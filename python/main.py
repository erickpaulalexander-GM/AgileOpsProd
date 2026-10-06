"""
Main entry point: runs the complete AgileOps Prod pipeline.

Excel → excel_reader → adapter → rules → kpi → renderer → workspace/output/

ADR-005: the 8h window is anchored dynamically to the last Excel update.

TWO SCOPES (explicit):
  - Timeline scope : only bars whose implementation start is inside the
                     dynamic 8h window. Feeds timeline + table.
  - KPI scope      : the in-scope pool set (column_map), one row per record,
                     NO dedup, evaluated with meta.updatedAt as the temporal
                     reference, and with TERMINAL states excluded (ADR-006).
                     Feeds the KPI cards and the diagnostic conflicts.

The frontend (web/*) is FROZEN and consumes only Data Contract v1.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from adapter import compute_window, filter_to_window, to_contract
from excel_reader import read_excel
from kpi import update_contract_kpis
from renderer import build_actions, render_dashboard
from rules import apply_rules, collect_conflicts, filter_operational, is_terminal

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


def main(excel_path: str | Path = DEFAULT_EXCEL_PATH) -> dict[str, Path]:
    """
    Run the complete AgileOps Prod pipeline.

    Args:
        excel_path: Path to the Excel file to process

    Returns:
        dict with output file paths
    """
    logger.info("Starting AgileOps Prod pipeline for: %s", excel_path)

    # Step 1: Read Excel (already filtered to the in-scope pools)
    data = read_excel(excel_path)
    rows_all = data["rows"]          # FULL in-scope set (KPI scope)
    diagnostic = data["diagnostic"]
    logger.info("Read %d in-scope rows (KPI scope)", len(rows_all))

    # v1.1.1: displayed "Actualización" = the Excel file modification time.
    # v1.1.2: this same timestamp filters the operational table (live work only).
    updated_at_dt = datetime.fromtimestamp(Path(excel_path).stat().st_mtime)
    updated_at_display = updated_at_dt.strftime("%Y-%m-%dT%H:%M:%S")
    logger.info("File mtime (displayed updatedAt): %s", updated_at_display)

    # Step 2: Compute dynamic window (ADR-005). v1.1.3: the single temporal
    # reference is the file mtime (meta.updatedAt), same as the header and table.
    window = compute_window(updated_at_dt)

    # Step 3: Apply business rules over the FULL in-scope set, using the
    #         snapshot reference (meta.updatedAt) — this is the KPI scope.
    rows_all = apply_rules(rows_all, reference_now=window["updated_at"])

    # Step 4: Timeline scope = only rows whose impl start is inside the window.
    #         (These share the same dict objects, so rule flags carry over.)
    rows_timeline, bars_outside = filter_to_window(rows_all, window)

    # Step 5: Convert to Data Contract v1.
    #   - Timeline scope: in-window rows.
    #   - Table scope: the full in-scope pool operational universe.
    contract = to_contract(
        rows_timeline,
        diagnostic,
        window,
        table_rows=rows_all,
        table_reference_dt=updated_at_dt,
    )

    # meta.updatedAt shows the Excel file modification date. This same stamp
    # also filters the operational table (live work only).
    contract["meta"]["updatedAt"] = updated_at_display

    # Step 6: Calculate KPIs over the FULL in-scope set (KPI scope, no dedup)
    contract = update_contract_kpis(contract, rows_all)

    # Step 7: Build action payload (ADR-008) and the diagnostic report
    actions = build_actions(rows_all, rows_timeline)
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
            "updatedAtSource": "excel_file_mtime",
            "timelineScope": {
                "description": "Bars whose impl start is inside the dynamic 8h window",
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
                "lateStarts": len(actions["lateStarts"]),
                "ratificationsSoon": len(actions["ratificationsSoon"]),
                "ratificationsExpired": len(actions["ratificationsExpired"]),
            },
        }
    )

    # Step 8: Generate output files
    output_paths = render_dashboard(contract, diagnostic, actions)

    _print_report(contract, diagnostic, output_paths)

    logger.info("Pipeline completed successfully!")
    return output_paths


def file_mtime_iso(path: str | Path) -> str:
    """Excel file modification time as ISO string (v1.1.1)."""
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
    print(f"  Última actualización del Excel : {contract['meta']['updatedAt']}")
    print(f"  Ventana dinámica (ADR-005)     : "
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
        print(f"    Pases atrasados                     : {ap.get('lateStarts', 0)}")
        print(f"    Ratificaciones por vencer           : {ap.get('ratificationsSoon', 0)}")
        print(f"    Ratificaciones vencidas             : {ap.get('ratificationsExpired', 0)}")
        print(line)
    print("  OUTPUT")
    for name, path in output_paths.items():
        print(f"    {name:<20} : {path}")
    print(line)
    print("  Pool order (meta.poolOrder, emitido por Python): "
          f"{', '.join(contract['meta']['poolOrder'])}")
    print(line)
    print("  Frontend: dashboard.js (tabla operativa); theme.css y timeline intactos.")
    print("  ADR-005 corregido (v1.1.3): referencia temporal única = mtime del Excel.")
    print(line)


if __name__ == "__main__":
    excel_file = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_EXCEL_PATH
    main(excel_file)
