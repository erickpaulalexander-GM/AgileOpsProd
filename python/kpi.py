"""
KPI calculation: computes dashboard metrics from annotated rows.

Reads rule flags (_late_start, _ratification_soon, _ratification_expired)
set by rules.py and produces the kpis section of the Data Contract.

Feature Freeze v1.0 (ADR-007):
  - Ratification KPIs use FIN_RATI as the ONLY end reference.
  - Reversions is a "PRÓXIMAMENTE" KPI: it does NOT read any Excel column.
    Its future source is JIRA. The contract field stays present (value 0)
    to keep the Data Contract v1 shape frozen.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ADR-007: reversions placeholder metadata (not sourced from Excel)
REVERSIONS_STATUS = "proximamente"
REVERSIONS_SOURCE = "JIRA"


def calculate_kpis(rows: list[dict[str, Any]]) -> dict[str, int]:
    """
    Calculate KPIs from annotated rows.

    Returns:
        dict with keys:
            - lateStarts: count of late starts
            - ratificationsSoon: count of ratifications about to start
            - ratificationsExpired: count of expired ratifications (vs FIN_RATI)
            - reversions: always 0 — "PRÓXIMAMENTE", future source = JIRA
    """
    late_starts = sum(1 for r in rows if r.get("_late_start", False))
    rat_soon = sum(1 for r in rows if r.get("_ratification_soon", False))
    rat_expired = sum(1 for r in rows if r.get("_ratification_expired", False))

    # ADR-007: reversions is a placeholder KPI. It never reads Excel columns;
    # the future source of truth is JIRA.
    reversions = 0

    kpis = {
        "lateStarts": late_starts,
        "ratificationsSoon": rat_soon,
        "ratificationsExpired": rat_expired,
        "reversions": reversions,
    }

    logger.info(
        f"KPIs: late={late_starts}, rati_soon={rat_soon}, "
        f"rati_expired={rat_expired}, reversions={reversions} ({REVERSIONS_STATUS}, source={REVERSIONS_SOURCE})"
    )

    return kpis


def update_contract_kpis(contract: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Update the kpis section of a Data Contract.

    Args:
        contract: Data Contract v1 dict (modified in-place)
        rows: Annotated rows from rules.py

    Returns:
        The updated contract
    """
    contract["kpis"] = calculate_kpis(rows)
    return contract
