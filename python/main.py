"""
Main entry point: runs the complete AgileOps Prod pipeline.

Excel → excel_reader → adapter → rules → kpi → renderer → workspace/output/

ADR-012 (supersedes ADR-005's Excel-mtime anchor): the 8h window is anchored
to the RUN CLOCK — the system time at which the pipeline runs — because the
dashboard is executed by Windows Task Scheduler. The Excel mtime is a copy
artifact (when the file landed on the machine), so it is kept in the
diagnostic report ONLY and never anchors the window. A run can be reproduced
exactly with ``--now "YYYY-MM-DD HH:MM"``.

TWO SCOPES (explicit):
  - Timeline scope : rows overlapping the dynamic 8h window — starts inside,
                     or started before with a valid FIN past the window edge
                     (T14, drawn clipped). Feeds timeline + table.
  - KPI scope      : the in-scope pool set (column_map), one row per record,
                     NO dedup, evaluated with meta.updatedAt as the temporal
                     reference, and with TERMINAL states excluded (ADR-006).
                     Feeds the KPI cards and the diagnostic conflicts.

The frontend (web/*) is FROZEN and consumes only Data Contract v1.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from adapter import compute_window, filter_to_window, to_contract
from config import (
    get_sheet,
    load_config,
    resolve_input_file,
    resolve_output_dir,
    wall_now,
)
import renderer as renderer_mod
from excel_reader import read_excel
from renderer import build_actions, filter_early_start, filter_in_flight, filter_stale_in_flight, render_dashboard
from kpi import update_contract_kpis, update_contract_visibility_kpis
from rules import apply_rules, collect_conflicts, filter_operational, is_terminal
from shifts import (
    SHIFT_FILE_PATTERN,
    build_lane_shifts,
    collect_out_of_shift,
    find_shifts_file,
    load_shifts,
)

# Repository root — this module lives in <root>/python/. Resolving the default
# input from here (not from the CWD) makes the pipeline runnable from anywhere.
REPO_ROOT = Path(__file__).resolve().parent.parent

# Default workbook for the AgileOps Prod pool universe.
DEFAULT_EXCEL_PATH = REPO_ROOT / "workspace" / "input" / "ControlPases.xlsx"


def _force_utf8_output() -> None:
    """Make stdout/stderr UTF-8 safe on Windows.

    When stdout/stderr are redirected (Task Scheduler, pipes, log files),
    Windows falls back to the ANSI codepage (e.g. cp1252), which cannot
    encode characters like ``→`` and crashes the report with
    UnicodeEncodeError. Reconfigure both streams to UTF-8 so the pipeline
    always exits 0 on the client machine (see dev-report.txt: Windows 11).
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            encoding = (getattr(stream, "encoding", "") or "").lower()
            if encoding.replace("-", "") not in ("utf8", "utf_8"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass  # stream does not support reconfiguration; leave as-is


_force_utf8_output()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _now() -> datetime:
    """The real system clock.

    Isolated behind a function so a run is reproducible: tests (and the CLI
    ``--now``) can swap or bypass the clock without touching the pipeline.
    """
    return datetime.now()


def _resolve_reference_now(
    reference_now: datetime | None, timezone: str | None = None
) -> datetime:
    """The SINGLE temporal reference of a run.

    Returns the explicit override when one was supplied, otherwise the
    wall-clock in the configured timezone (default America/Lima, naive).
    Every downstream consumer (window, rules, table filter,
    meta.updatedAt) flows from this one value.
    """
    if reference_now is not None:
        return reference_now
    if timezone:
        base = _now()
        lima = wall_now(timezone)
        # Compat con el seam de tests (monkeypatch de _now): si el reloj fue
        # fijado a un valor lejos del presente real, se honra tal cual.
        try:
            far = abs((base - datetime.now()).total_seconds()) > 300
        except TypeError:
            far = False
        if far:
            return base
        return lima
    return _now()


# Accepted ``--now`` formats, most specific first. The bare "%H:%M" form is
# resolved against today's date so a quick manual replay is possible.
_NOW_FORMATS: tuple[str, ...] = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%d/%m/%Y %H:%M",
    "%H:%M",
)


def _parse_now(value: str) -> datetime:
    """Parse the CLI ``--now`` override into a datetime.

    Forgiving about the separator (``2026-10-06 09:55`` and
    ``2026-10-06T09:55`` both work). An unparseable value raises
    ``argparse.ArgumentTypeError`` so the CLI fails LOUDLY instead of silently
    falling back to the clock.
    """
    text = str(value).strip()
    for fmt in _NOW_FORMATS:
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if fmt == "%H:%M":
            today = datetime.now()
            parsed = parsed.replace(
                year=today.year, month=today.month, day=today.day
            )
        return parsed
    raise argparse.ArgumentTypeError(
        f"invalid --now value {value!r}; "
        'expected e.g. "2026-10-06 09:55"'
    )


def _build_arg_parser() -> argparse.ArgumentParser:
    """CLI: ``main.py [excel_path] [--now DATETIME] [--config PATH]``."""
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Generate the AgileOps Prod dashboard from an Excel workbook.",
    )
    parser.add_argument(
        "excel_path",
        nargs="?",
        default=None,
        help=(
            "Path to the Excel workbook "
            "(default: config paths.input_dir + excel.pattern)."
        ),
    )
    parser.add_argument(
        "--config",
        dest="config_path",
        default=None,
        metavar="PATH",
        help="Path to config.yaml (default: <repo>/config.yaml).",
    )
    parser.add_argument(
        "--now",
        dest="reference_now",
        type=_parse_now,
        default=None,
        metavar="DATETIME",
        help=(
            "Override the run clock, e.g. --now \"2026-10-06 09:55\". "
            "Without it the real system clock anchors the window."
        ),
    )
    return parser


def cli(argv: list[str] | None = None) -> int:
    """Parse CLI arguments and run the pipeline. Returns the exit code.

    ``python/main.py`` (no arguments) keeps working: the default input path is
    resolved from the repository root (ADR-010), which is the form Task
    Scheduler uses.
    """
    args = _build_arg_parser().parse_args(argv)
    main(
        args.excel_path,
        reference_now=args.reference_now,
        config_path=args.config_path,
    )
    return 0


def main(
    excel_path: str | Path | None = None,
    reference_now: datetime | None = None,
    config_path: str | Path | None = None,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Path]:
    """
    Run the complete AgileOps Prod pipeline.

    Args:
        excel_path: Path to the Excel file to process
        reference_now: Explicit temporal reference for the whole run. When
            None (the default), the real system clock is used. Supplying it
            is how a run is reproduced exactly — the CLI ``--now`` flag.

    Returns:
        dict with output file paths
    """
    if cfg is None:
        cfg = load_config(config_path)
    resolved_excel = resolve_input_file(cfg, explicit=excel_path)
    sheet = get_sheet(cfg)
    cfg_output = resolve_output_dir(cfg)
    # Compat: los tests parchean renderer.OUTPUT_DIR al tmp dir. Si el modulo
    # fue parcheado (difiere del default), manda el modulo; si no, manda cfg.
    default_out = (renderer_mod.REPO_ROOT / "workspace" / "output").resolve()
    try:
        use_module_out = Path(renderer_mod.OUTPUT_DIR).resolve() != default_out
    except OSError:
        use_module_out = False
    if use_module_out:
        output_dir = Path(renderer_mod.OUTPUT_DIR)
    else:
        output_dir = cfg_output
    app_name = str(cfg.get("app", {}).get("name", "AgileOps Prod Console"))
    timezone = str(cfg.get("app", {}).get("timezone", "America/Lima"))
    environment = str(cfg.get("environment", "DEV"))
    logger.info(
        "Starting %s pipeline for: %s (env=%s, config=%s)",
        app_name,
        resolved_excel,
        environment,
        cfg.get("_config_path", "defaults"),
    )

    # Step 1: Read Excel (already filtered to the in-scope pools)
    data = read_excel(resolved_excel, sheet=sheet)
    rows_all = data["rows"]          # FULL in-scope set (KPI scope)
    diagnostic = data["diagnostic"]
    logger.info("Read %d in-scope rows (KPI scope)", len(rows_all))

    # ADR-012: the SINGLE temporal reference of the whole dashboard is the run
    # clock, captured ONCE here. Every downstream consumer — the window, the
    # rules' reference_now, the table's live-work filter and meta.updatedAt —
    # flows from this one value. The Excel mtime is NOT a reference; it is
    # reported separately in the diagnostic so a stale file can be spotted.
    anchor_dt = _resolve_reference_now(reference_now, timezone=timezone)
    updated_at_display = anchor_dt.strftime("%Y-%m-%dT%H:%M:%S")
    logger.info("Run reference (meta.updatedAt): %s", updated_at_display)

    # Step 2: Compute the dynamic 8h window (ADR-012) from that single
    # reference. The window is the floor of the run clock.
    window = compute_window(anchor_dt)

    # Step 3: Apply business rules over the FULL in-scope set, using the run
    #         reference (meta.updatedAt) — this is the KPI scope.
    rows_all = apply_rules(rows_all, reference_now=window["updated_at"])

    # Step 4: Timeline scope = rows overlapping the window (starts inside,
    #         or started before with proven overlap — T14 clipped in-flight).
    #         (These share the same dict objects, so rule flags carry over.)
    rows_timeline, bars_outside = filter_to_window(rows_all, window)

    # T5: En-vuelo scope = pases en curso cubriendo la referencia, sobre el
    # universo operativo completo (NO solo la ventana: un pase iniciado
    # antes de la ventana sigue volando). Es el KPI "Pases en vuelo".
    rows_in_flight = filter_in_flight(rows_all, anchor_dt)
    logger.info("In-flight now (Pases en curso): %d", len(rows_in_flight))

    # T6: Colgados = en curso con FIN pasado. Fuera de tabla y drawers
    # (salvo rati vencida de casualidad); en timeline solo como recorte si
    # solapan su borde izquierdo (T14). El drawer propio sigue siendo el
    # lugar para accionarlos.
    rows_stale = filter_stale_in_flight(rows_all, anchor_dt)
    logger.info("Stale in-flight (Fuera de ventana): %d", len(rows_stale))

    # T20: Adelantados = en curso con INI futuro (caso OCD-231277).
    rows_early = filter_early_start(rows_all, anchor_dt)
    logger.info("Early start (Adelantados): %d", len(rows_early))

    # T18: Turnos por carril — sombreado fuera de turno + pases anómalos.
    # Sin archivo o con archivo roto: degradado (sin sombreado), nunca crash.
    shifts_pattern = str(cfg.get("shifts", {}).get("file", SHIFT_FILE_PATTERN))
    shifts_path = find_shifts_file(Path(cfg["paths"]["input_dir"]), shifts_pattern)
    shifts_people: list = []
    shifts_source = "none"
    if shifts_path is not None:
        try:
            shifts_people = load_shifts(shifts_path)["people"]
            shifts_source = str(shifts_path)
        except (OSError, ValueError, KeyError) as exc:
            logger.warning("Turnos no cargados (%s); sin sombreado", exc)
    lane_shifts = build_lane_shifts(
        rows_timeline, shifts_people, window["start"], window["end"]
    )
    out_of_shift = collect_out_of_shift(rows_all, shifts_people)
    matched_lanes = sum(
        1
        for lanes in lane_shifts.values()
        for lane in lanes.values()
        if lane["matched"]
    )
    total_lanes = sum(len(lanes) for lanes in lane_shifts.values())
    logger.info(
        "Shift lanes: %d/%d matched (%s); out-of-shift: %d",
        matched_lanes,
        total_lanes,
        shifts_source,
        len(out_of_shift),
    )

    # Step 5: Convert to Data Contract v1.
    #   - Timeline scope: overlapping rows (T14, clipped geometry).
    #   - Table scope: the full in-scope pool operational universe.
    contract = to_contract(
        rows_timeline,
        diagnostic,
        window,
        table_rows=rows_all,
        table_reference_dt=anchor_dt,
    )

    # meta.updatedAt is the run reference (ADR-012). This same stamp also
    # filters the operational table (live work only).
    contract["meta"]["updatedAt"] = updated_at_display

    # Step 6: Calculate KPIs over the FULL in-scope set (KPI scope, no dedup)
    contract = update_contract_kpis(contract, rows_all)

    # Step 6b: Per-visibility-group KPIs + action ticket scopes (ADR-011).
    # Without this the KPI cards would keep showing the aggregate of ALL pools,
    # leaking the hidden pools' counts through the selector.
    contract = update_contract_visibility_kpis(
        contract,
        rows_all,
        rows_timeline,
        in_flight_rows=rows_in_flight,
        stale_in_flight_rows=rows_stale,
        early_start_rows=rows_early,
    )

    # Step 7: Build action payload (ADR-008) and the diagnostic report
    actions = build_actions(
        rows_all,
        rows_timeline,
        in_flight_rows=rows_in_flight,
        stale_in_flight_rows=rows_stale,
        early_start_rows=rows_early,
    )
    operational_rows = filter_operational(rows_all)  # ADR-006
    conflicts = collect_conflicts(rows_all)          # only non-terminal pairs
    responsables = _collect_responsables(operational_rows)

    terminal_breakdown: dict[str, int] = {}
    for r in rows_all:
        if is_terminal(r.get("estado", "")):
            key = str(r.get("estado", "")).strip()
            terminal_breakdown[key] = terminal_breakdown.get(key, 0) + 1

    pool_counts = {
        pool["pool"]: len(pool["bars"]) for pool in contract["timeline"]
    }

    diagnostic.update(
        {
            "windowStart": window["start_hhmm"],
            "windowEnd": window["end_hhmm"],
            "windowAnchor": window["updated_at"].strftime("%Y-%m-%dT%H:%M:%S"),
            "displayedUpdatedAt": updated_at_display,
            # Truthful provenance of the anchor: an organic scheduled run uses
            # the real clock; a reproduced run was pinned with --now. The Excel
            # mtime is NOT the anchor (ADR-012) and is reported separately below.
            "updatedAtSource": (
                "now_override" if reference_now is not None else "run_clock"
            ),
            # Excel mtime — DIAGNOSTIC ONLY. Useful to spot a stale file in a
            # scheduled run; it never reaches the window, the rules or the table.
            "excelFileMtime": file_mtime_iso(resolved_excel),
            "excelFileMtimeSource": "excel_file_mtime",
            # T8: el header del dash evidencia el archivo fuente (nombre +
            # mtime) para juzgar frescura. Solo diagnostico, nunca contrato.
            "excelFileName": Path(resolved_excel).name,
            "environment": environment,
            "configSource": str(cfg.get("_config_path", "defaults")),
            "configKind": str(cfg.get("_source", "defaults")),
            "timezone": timezone,
            "excelSheet": sheet,
            "excelPattern": str(cfg.get("excel", {}).get("pattern", "")),
            "timelineScope": {
                "description": "Bars overlapping the dynamic 8h window (starts inside, or started before with valid FIN past its edge — T14, drawn clipped)",
                "barsInWindow": len(rows_timeline),
                "barsOutsideWindow": bars_outside,
                "ticketsInTimeline": sum(len(p["bars"]) for p in contract["timeline"]),
                "pools": pool_counts,
            },
            "tableScope": {
                "description": (
                    "AgileOps Prod operational table: resource whitelist "
                    "+ ACTIVE states only (Coordinado / Pase en curso) "
                    "+ live-work temporal filter, sorted by start"
                ),
                "rowsInTable": len(contract["table"]),
                "pools": sorted({e["pool"] for e in contract["table"]}),
                "includedStates": ["Coordinado", "Pase en curso"],
                "temporalFilter": {
                    "field": "FEC. HORA. FIN. IMPL",
                    "operator": ">=",
                    "reference": updated_at_display,
                },
                "excludedStates": [
                    "Rechazado por Gestor de cambio",
                    "Rechazado",
                    "Pre Registrado",
                    "Registrado",
                    "Aprobado LT",
                    "Aprobado CL QA",
                    "Aprobado CL DEV",
                    "Aprobado PO",
                ],
            },
            "kpiScope": {
                "description": (
                    "Operational in-scope pool subset — terminal states excluded "
                    "(ADR-006), one row per record, reference = updatedAt"
                ),
                "referenceNow": window["updated_at"].strftime("%Y-%m-%dT%H:%M:%S"),
                "rowsEvaluated": len(rows_all),
                "operationalRows": len(operational_rows),
                "excludedTerminal": len(rows_all) - len(operational_rows),
                "terminalStatesExcluded": terminal_breakdown,
                "lateStarts": contract["kpis"]["lateStarts"],
                "ratificationsSoon": contract["kpis"]["ratificationsSoon"],
                "ratificationsExpired": contract["kpis"]["ratificationsExpired"],
                "reversions": contract["kpis"]["reversions"],
                "reversionsStatus": "proximamente",
                "reversionsSource": "JIRA",
                "conflictsDetected": len(conflicts),
                "responsablesDetected": len(responsables),
            },
            "conflicts": conflicts,
            "actionPayload": {
                "passesInWindow": len(actions["passesInWindow"]),
                "inFlightNow": len(actions["inFlightNow"]),
                "staleInFlight": len(actions["staleInFlight"]),
                "earlyStart": len(actions["earlyStart"]),
                "lateStarts": len(actions["lateStarts"]),
                "ratificationsSoon": len(actions["ratificationsSoon"]),
                "ratificationsExpired": len(actions["ratificationsExpired"]),
            },
            "shiftScope": {
                "description": (
                    "Turnos por carril (T18): carriles matcheados y pases "
                    "fuera de todo turno (anomalia, solo diagnostico)"
                ),
                "shiftsFile": shifts_source,
                "lanesMatched": matched_lanes,
                "lanesTotal": total_lanes,
                "outOfShift": len(out_of_shift),
                "outOfShiftTickets": out_of_shift,
            },
        }
    )

    # Step 8: Generate output files
    output_paths = render_dashboard(
        contract,
        diagnostic,
        actions,
        output_dir=output_dir,
        dashboard_title=app_name,
        resource_shifts=lane_shifts,
    )

    _print_report(contract, diagnostic, output_paths)

    logger.info("Pipeline completed successfully!")
    return output_paths


def file_mtime_iso(path: str | Path) -> str:
    """Excel file modification time as an ISO string.

    DIAGNOSTIC ONLY (ADR-012): this value lands in ``diagnostic_report.json``
    as ``excelFileMtime`` so a stale workbook can be spotted in a scheduled
    run. It never anchors the window, the rules or the table filter.
    """
    return datetime.fromtimestamp(
        Path(path).stat().st_mtime
    ).strftime("%Y-%m-%dT%H:%M:%S")


def _collect_responsables(rows: list[dict[str, Any]]) -> set[str]:
    """Unique non-empty responsables (KPI scope)."""
    result: set[str] = set()
    for r in rows:
        value = str(r.get("responsable", "")).strip()
        if value and value.lower() != "nan":
            result.add(value)
    return result


def _print_report(
    contract: dict[str, Any],
    diagnostic: dict[str, Any],
    output_paths: dict[str, Path],
) -> None:
    """Print the final Phase 3 report with explicit scope separation."""
    tl = diagnostic["timelineScope"]
    kp = diagnostic["kpiScope"]
    line = "=" * 66

    print("\n" + line)
    print("  AGILEOPS PROD CONSOLE — PIPELINE REPORT")
    print(line)
    print(f"  Referencia de ejecución (reloj): {contract['meta']['updatedAt']}")
    print(f"  Ventana dinámica (ADR-012)     : "
          f"{contract['meta']['windowStart']} → {contract['meta']['windowEnd']}")
    print(line)
    print("  PROCESAMIENTO")
    print(f"    Filas leídas (Excel total)          : {diagnostic['rowsRead']}")
    print(f"    Filas en scope (pools AgileOps Prod): {diagnostic['rowsAfterFilter']}")
    print(f"    Filas ignoradas (fuera de scope)    : {diagnostic['rowsIgnored']}")
    print(f"    Fechas inválidas                    : {diagnostic['invalidDates']}")
    print(line)
    print("  SCOPE DEL TIMELINE  (ventana visible)")
    print(f"    Barras en ventana                   : {tl['barsInWindow']}")
    print(f"    Barras fuera de ventana             : {tl['barsOutsideWindow']}")
    print(f"    Tickets en timeline                 : {tl['ticketsInTimeline']}")
    for pool, n in tl["pools"].items():
        print(f"      {pool:<15} : {n} barras")
    print(line)
    ts = diagnostic.get("tableScope", {})
    if ts:
        print("  SCOPE DE LA TABLA  (universo operativo AgileOps Prod)")
        print(f"    Filas en tabla                      : {ts.get('rowsInTable', 0)}")
        print(f"    Filtro temporal                     : FIN IMPL ≥ {ts.get('temporalFilter', {}).get('reference', '?')}")
        print(f"    Pools                               : {', '.join(ts.get('pools', []))}")
        print(line)
    print("  SCOPE DE KPIs  (in-scope operativo — terminales excluidos, ADR-006)")
    print(f"    Referencia temporal (updatedAt)     : {kp['referenceNow']}")
    print(f"    Filas en scope evaluadas            : {kp['rowsEvaluated']}")
    print(f"    Filas operativas                    : {kp['operationalRows']}")
    print(f"    Excluidas por estado terminal       : {kp['excludedTerminal']}")
    if kp.get("terminalStatesExcluded"):
        for state, n in kp["terminalStatesExcluded"].items():
            print(f"        - {state:<28} : {n}")
    print(f"    Responsables detectados             : {kp['responsablesDetected']}")
    print(f"    Inicios atrasados                   : {kp['lateStarts']}")
    print(f"    Ratificaciones por vencer           : {kp['ratificationsSoon']}")
    print(f"    Ratificaciones vencidas             : {kp['ratificationsExpired']}")
    print(f"    Reversiones                         : {kp['reversions']} (próximamente · fuente {kp.get('reversionsSource', 'JIRA')})")
    print(f"    Conflictos detectados               : {kp['conflictsDetected']}")
    print(line)
    ap = diagnostic.get("actionPayload", {})
    if ap:
        print("  ACTION PAYLOAD — window.ChangeOpsActions (ADR-008)")
        print(f"    Pases en ventana                    : {ap.get('passesInWindow', 0)}")
        print(f"    Pases en curso (volando ahora)       : {ap.get('inFlightNow', 0)}")
        print(f"    Pases fuera de ventana (FIN pasado)  : {ap.get('staleInFlight', 0)}")
        print(f"    Pases adelantados (INI futuro)       : {ap.get('earlyStart', 0)}")
        print(f"    Pases atrasados                     : {ap.get('lateStarts', 0)}")
        print(f"    Ratificaciones por vencer           : {ap.get('ratificationsSoon', 0)}")
        print(f"    Ratificaciones vencidas             : {ap.get('ratificationsExpired', 0)}")
        print(line)
    print("  OUTPUT")
    for name, path in output_paths.items():
        print(f"    {name:<20} : {path}")
    print(line)
    ss = diagnostic.get("shiftScope", {})
    if ss:
        print(f"  Turnos ({ss.get('shiftsFile', 'none')}): "
              f"{ss.get('lanesMatched', 0)}/{ss.get('lanesTotal', 0)} carriles, "
              f"{ss.get('outOfShift', 0)} pases fuera de turno")
        print(line)
    print("  Pool order (meta.poolOrder, emitido por Python): "
          f"{', '.join(contract['meta']['poolOrder'])}")
    groups = (contract.get("meta") or {}).get("visibilityGroups") or []
    if groups:
        print("  Visibility groups (meta.visibilityGroups, ADR-011):")
        for group in groups:
            kpis = group.get("kpis") or {}
            tickets = group.get("tickets") or {}
            print(f"    {group['id']:<10} {group['label']:<10} "
                  f"familias={', '.join(group['families'])}  "
                  f"pases_en_ventana={len(tickets.get('passesInWindow', []))}  "
                  f"en_curso={len(tickets.get('inFlightNow', []))}  "
                  f"fuera_ventana={len(tickets.get('staleInFlight', []))}  "
                  f"atrasados={kpis.get('lateStarts', 0)}  "
                  f"rati_por_vencer={kpis.get('ratificationsSoon', 0)}  "
                  f"rati_vencidas={kpis.get('ratificationsExpired', 0)}")
        print("    (filtro de presentacion, NO control de acceso - ver ADR-011)")
    print(line)
    print("  Frontend: dashboard.js (tabla operativa); theme.css y timeline intactos.")
    print("  ADR-012: la ventana se ancla al reloj de ejecución (reemplaza ADR-005).")
    mtime = diagnostic.get("excelFileMtime", "?")
    print(f"  Excel mtime (solo diagnóstico) : {mtime}")
    print(line)


if __name__ == "__main__":
    sys.exit(cli())
