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
) -> dict[str, Any]:
    """
    Build the window.ChangeOpsActions payload (ADR-008).

    No business rules are added here: the lists are derived from the rule
    flags already computed by rules.py (`_late_start`, `_ratification_soon`,
    `_ratification_expired`).
    """
    return {
        "passesInWindow": [_action_record(r, "impl") for r in rows_in_window],
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
