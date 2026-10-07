"""
Renderer: generates output files from the Data Contract.

Outputs (all under workspace/output/, created if missing):
- dashboard.html — self-contained HTML (template + embedded data)
- dashboard_data.json — the Data Contract v1
- diagnostic_report.json — processing statistics

ADR-008: in addition to the Data Contract v1 (window.MockOperations.data),
the renderer emits window.ChangeOpsActions — a separate, informational action
payload for the KPI Action Drawers. The Data Contract shape is NOT modified.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Paths — resolved from the repository root so the pipeline runs from any CWD.
REPO_ROOT = Path(__file__).resolve().parent.parent

# Estado que cuenta como "en vuelo": el pase se esta ejecutando ahora mismo
# (T5, pedido del cliente). Comparacion normalizada como la tabla.
IN_FLIGHT_STATE = "pase en curso"


def _norm_estado(value: Any) -> str:
    """Lowercase + whitespace colapsado para comparar estados."""
    return " ".join(str(value or "").split()).lower()


def is_in_flight_now(row: dict[str, Any], reference: datetime) -> bool:
    """True si el pase se ejecuta en `reference`: en curso y cubriendolo.

    Subconjunto de la tabla operativa (mismo universo: estados activos +
    trabajo vivo), restringido a estado en curso ya iniciado. Las fechas
    ausentes/invalidas no cuentan — igual que la tabla, que exige ambas.
    """
    if _norm_estado(row.get("estado")) != IN_FLIGHT_STATE:
        return False
    inicio = row.get("inicio_impl")
    fin = row.get("fin_impl")
    if not isinstance(inicio, datetime) or not isinstance(fin, datetime):
        return False
    return inicio <= reference <= fin


def filter_in_flight(
    rows: list[dict[str, Any]], reference: datetime
) -> list[dict[str, Any]]:
    """Pases en vuelo sobre el universo operativo (ver is_in_flight_now)."""
    return [r for r in rows if is_in_flight_now(r, reference)]


def is_stale_in_flight(row: dict[str, Any], reference: datetime) -> bool:
    """True si el pase quedo colgado en curso con el FIN ya pasado.

    T6: son los tickets fantasma — fuera de timeline (inicio viejo), fuera
    de tabla (fin pasado) y fuera de drawers, salvo ratificacion vencida
    de casualidad. Sin FIN valido no se juzga: no se puede probar pasado.
    """
    if _norm_estado(row.get("estado")) != IN_FLIGHT_STATE:
        return False
    fin = row.get("fin_impl")
    if not isinstance(fin, datetime):
        return False
    return fin < reference


def filter_stale_in_flight(
    rows: list[dict[str, Any]], reference: datetime
) -> list[dict[str, Any]]:
    """Pases colgados en curso (ver is_stale_in_flight)."""
    return [r for r in rows if is_stale_in_flight(r, reference)]
WEB_DIR = REPO_ROOT / "web"
TEMPLATE_PATH = WEB_DIR / "dashboard_template.html"
OUTPUT_DIR = REPO_ROOT / "workspace" / "output"

# The <title> in web/dashboard_template.html replaced below. Both strings must
# stay byte-identical: renderer.py substitutes it with the app name + updatedAt.
TEMPLATE_TITLE_TAG = "<title>AgileOps Prod Console</title>"
DASHBOARD_TITLE = "AgileOps Prod Console"


def _fmt_dt(dt: Any) -> str:
    """Format a datetime as 'DD/MM/YYYY HH:MM' (Excel display style)."""
    if isinstance(dt, datetime):
        return dt.strftime("%d/%m/%Y %H:%M")
    return ""


def _action_record(row: dict[str, Any], kind: str) -> dict[str, Any]:
    """
    Map one row to an action record (ADR-008).

    kind:
      - "impl"      : implementation drawer (INI/FIN IMPL)
      - "rati"      : ratification drawer (INI/FIN RATI)
      - "rati_total": ratification-expired drawer (+ FIN RATI TOTAL, informational)
    """
    record = {
        "ticket": str(row.get("ticket", "") or ""),
        "app": str(row.get("nombre_app", "") or ""),
        "resource": str(row.get("responsable", "") or ""),
        "status": str(row.get("estado", "") or ""),
    }
    if kind == "impl":
        record["iniImpl"] = _fmt_dt(row.get("inicio_impl"))
        record["finImpl"] = _fmt_dt(row.get("fin_impl"))
    elif kind == "rati":
        record["iniRati"] = _fmt_dt(row.get("inicio_rati"))
        record["finRati"] = _fmt_dt(row.get("fin_rati"))
    elif kind == "rati_total":
        record["iniRati"] = _fmt_dt(row.get("inicio_rati"))
        record["finRati"] = _fmt_dt(row.get("fin_rati"))
        # ADR-008: informational only — never used by KPIs or rules.
        record["endRatiTotal"] = _fmt_dt(row.get("fin_rati_total"))
    return record


def build_actions(
    rows_r1: list[dict[str, Any]],
    rows_in_window: list[dict[str, Any]],
    in_flight_rows: list[dict[str, Any]] | None = None,
    stale_in_flight_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Build the window.ChangeOpsActions payload (ADR-008).

    No business rules are added here: the lists are derived from the rule
    flags already computed by rules.py (`_late_start`, `_ratification_soon`,
    `_ratification_expired`) — except `inFlightNow` (T5 en-vuelo scope) and
    `staleInFlight` (T6 colgados: en curso con FIN pasado), both precomputed
    by the caller with filter_in_flight() / filter_stale_in_flight() over the
    operational universe.
    """
    return {
        "passesInWindow": [_action_record(r, "impl") for r in rows_in_window],
        "inFlightNow": [_action_record(r, "impl") for r in (in_flight_rows or [])],
        "staleInFlight": [
            _action_record(r, "impl") for r in (stale_in_flight_rows or [])
        ],
        "lateStarts": [
            _action_record(r, "impl") for r in rows_r1 if r.get("_late_start")
        ],
        "ratificationsSoon": [
            _action_record(r, "rati") for r in rows_r1 if r.get("_ratification_soon")
        ],
        "ratificationsExpired": [
            _action_record(r, "rati_total")
            for r in rows_r1
            if r.get("_ratification_expired")
        ],
    }


def render_dashboard(
    contract: dict[str, Any],
    diagnostic: dict[str, Any],
    actions: dict[str, Any] | None = None,
    output_dir: str | Path | None = None,
    dashboard_title: str | None = None,
) -> dict[str, Path]:
    """
    Generate all output files.

    Args:
        contract: Data Contract v1
        diagnostic: Processing statistics
        actions: Optional window.ChangeOpsActions payload (ADR-008)
        output_dir: Override for OUTPUT_DIR (config paths.output_dir)
        dashboard_title: Override for DASHBOARD_TITLE (config app.name)

    Returns:
        dict with output file paths
    """
    out = Path(output_dir) if output_dir is not None else OUTPUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    title = dashboard_title or DASHBOARD_TITLE

    # 1. Write dashboard_data.json
    data_path = out / "dashboard_data.json"
    data_path.write_text(
        json.dumps(contract, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(f"Written: {data_path}")

    # 2. Write diagnostic_report.json
    diag_path = out / "diagnostic_report.json"
    diag_path.write_text(
        json.dumps(diagnostic, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(f"Written: {diag_path}")

    # 3. Generate dashboard.html (template + inline data)
    html_path = out / "dashboard.html"
    _generate_html(contract, actions, html_path, title=title)
    logger.info(f"Written: {html_path}")

    return {
        "dashboard_html": html_path,
        "dashboard_data": data_path,
        "diagnostic_report": diag_path,
    }


def _generate_html(
    contract: dict[str, Any],
    actions: dict[str, Any] | None,
    output_path: Path,
    title: str = DASHBOARD_TITLE,
) -> None:
    """
    Generate a self-contained dashboard.html.

    Strategy: read the template, inline all CSS/JS and embed the data contract
    so the file works standalone (SharePoint compatible).

    ADR-008: also embeds window.ChangeOpsActions (informational action payload)
    without touching the Data Contract v1 shape.
    """
    # Read template
    template = TEMPLATE_PATH.read_text(encoding="utf-8")

    # Read CSS files
    theme_css = (WEB_DIR / "theme.css").read_text(encoding="utf-8")
    timeline_css = (WEB_DIR / "components" / "timeline" / "timeline.css").read_text(encoding="utf-8")

    # Read JS files
    timeline_js = (WEB_DIR / "components" / "timeline" / "timeline.js").read_text(encoding="utf-8")
    dashboard_js = (WEB_DIR / "dashboard.js").read_text(encoding="utf-8")

    # Embed data contract in the shape the FROZEN frontend consumes.
    # web/dashboard.js reads: window.MockOperations.data
    data_script = (
        '<script>window.MockOperations = { data: '
        + json.dumps(contract, ensure_ascii=False)
        + ' };</script>\n'
    )

    # ADR-008: separate, non-contract action payload.
    if actions is not None:
        data_script += (
            '<script>window.ChangeOpsActions = '
            + json.dumps(actions, ensure_ascii=False)
            + ';</script>\n'
        )

    # Replace external resource references with inlined content
    html = template

    # Replace CSS links with inline styles
    html = html.replace(
        '<link rel="stylesheet" href="theme.css">',
        f'<style>\n{theme_css}\n</style>',
    )
    html = html.replace(
        '<link rel="stylesheet" href="components/timeline/timeline.css">',
        f'<style>\n{timeline_css}\n</style>',
    )

    # Replace JS script tags with inline scripts (except mock-operations)
    html = html.replace(
        '<script src="data/mock-operations.js"></script>',
        data_script,
    )
    html = html.replace(
        '<script src="components/timeline/timeline.js"></script>',
        f'<script>\n{timeline_js}\n</script>',
    )
    html = html.replace(
        '<script src="dashboard.js"></script>',
        f'<script>\n{dashboard_js}\n</script>',
    )

    # Update title
    html = html.replace(
        TEMPLATE_TITLE_TAG,
        f'<title>{title} — {contract["meta"]["updatedAt"]}</title>',
    )
    if TEMPLATE_TITLE_TAG in html:
        logger.warning(
            "Template title tag not found — dashboard.html keeps the raw title. "
            "Keep TEMPLATE_TITLE_TAG and web/dashboard_template.html in sync."
        )

    output_path.write_text(html, encoding="utf-8")
