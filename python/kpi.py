"""
KPI calculation: computes dashboard metrics from annotated rows.

Reads rule flags (_late_start, _ratification_soon, _ratification_expired)
set by rules.py and produces the kpis section of the Data Contract.

Feature Freeze v1.0 (ADR-007):
  - Ratification KPIs use FIN_RATI as the ONLY end reference.
  - Reversions is a "PRÓXIMAMENTE" KPI: it does NOT read any Excel column.
    Its future source is JIRA. The contract field stays present (value 0)
    to keep the Data Contract v1 shape frozen.

ADR-011: the global kpis object counts the whole in-scope pool set, so hiding
         other pools in the UI would still leak their aggregate counts. Each
         visibility group therefore carries its own kpis object plus the ticket
         scopes the action drawers filter on. Same counters, same rule flags,
         rows restricted to the group's pool families.
"""

from __future__ import annotations

import logging
from typing import Any

from column_map import get_visibility_group

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


# ---------------------------------------------------------------
# Per-visibility-group KPIs and action scopes (ADR-011)
# ---------------------------------------------------------------
# The global `kpis` object counts the WHOLE in-scope pool set, so a dashboard
# that hides other pools would still leak their aggregate counts through the KPI
# cards. Each visibility group therefore carries its own KPI object, computed by
# the SAME counters over the SAME rule flags, restricted to the rows of that
# group's pool families.
#
# `tickets` is the equivalent for the action drawers (ADR-008). window.ChangeOpsActions
# is one global payload and its records carry no pool field, so instead of
# duplicating the records the contract publishes, per group, the TICKET IDs that
# belong to it. The web layer filters the global payload by membership, which
# keeps a single source of record data and still scopes every drawer.

ACTION_SCOPES = (
    ("passesInWindow", None),          # every row in the 8h window
    ("lateStarts", "_late_start"),
    ("ratificationsSoon", "_ratification_soon"),
    ("ratificationsExpired", "_ratification_expired"),
)


def _row_ticket(row: dict[str, Any]) -> str:
    return str(row.get("ticket", "") or "").strip()


def calculate_group_kpis(rows: list[dict[str, Any]]) -> dict[str, int]:
    """KPI counters for one group — the same counters as the global object."""
    return calculate_kpis(rows)


def group_ticket_scopes(
    rows: list[dict[str, Any]],
    window_rows: list[dict[str, Any]],
    in_flight_rows: list[dict[str, Any]] | None = None,
    stale_in_flight_rows: list[dict[str, Any]] | None = None,
) -> dict[str, list[str]]:
    """
    Ticket IDs of one visibility group, per action scope.

    Mirrors renderer.build_actions() exactly: the in-window scope uses the
    window rows, the three alert scopes use the full in-scope set filtered by
    the same rule flags the global payload is built from. A flag reads False for
    terminal rows (ADR-006), so terminal rows never enter a group scope.
    The en-vuelo (T5) and colgados (T6) scopes use their precomputed rows.
    """
    scopes: dict[str, list[str]] = {}

    for name, flag in ACTION_SCOPES:
        source = window_rows if flag is None else rows
        tickets: list[str] = []
        for row in source:
            if flag is not None and not row.get(flag, False):
                continue
            ticket = _row_ticket(row)
            if ticket:
                tickets.append(ticket)
        scopes[name] = tickets

    scopes["inFlightNow"] = [
        ticket
        for row in (in_flight_rows or [])
        if (ticket := _row_ticket(row))
    ]
    scopes["staleInFlight"] = [
        ticket
        for row in (stale_in_flight_rows or [])
        if (ticket := _row_ticket(row))
    ]

    return scopes


def update_contract_visibility_kpis(
    contract: dict[str, Any],
    rows: list[dict[str, Any]],
    window_rows: list[dict[str, Any]],
    in_flight_rows: list[dict[str, Any]] | None = None,
    stale_in_flight_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Attach per-visibility-group KPIs and action ticket scopes to the contract.

    Reads the group definitions emitted by adapter.to_contract() into
    meta.visibilityGroups and adds `kpis` and `tickets` to each entry, matching
    rows to groups through column_map.get_visibility_group() so the group
    membership rule stays in one place.

    Row→group bucketing is O(rows) per group and each row belongs to at most one
    group (the groups are a partition), so a row's flag is never counted twice.
    Rows outside every group contribute to the global KPIs only — which is why
    the global object is NOT always the sum of the groups.

    A contract without meta.visibilityGroups (an older generated file) is left
    untouched rather than raising: the web layer degrades to the unfiltered
    dashboard.

    Args:
        contract: Data Contract v1 dict (modified in-place)
        rows: FULL in-scope annotated rows (KPI scope)
        window_rows: In-window annotated rows (timeline / passesInWindow scope)
        in_flight_rows: En-vuelo rows (T5, renderer.filter_in_flight scope)
        stale_in_flight_rows: Colgados rows (T6, renderer.filter_stale_in_flight)

    Returns:
        The updated contract
    """
    groups = (contract.get("meta") or {}).get("visibilityGroups")
    if not isinstance(groups, list):
        logger.info(
            "No meta.visibilityGroups in the contract — per-group KPIs skipped "
            "(ADR-011)"
        )
        return contract

    # Bucket rows by group id once, then derive both payloads per group.
    rows_by_group: dict[str, list[dict[str, Any]]] = {}
    window_by_group: dict[str, list[dict[str, Any]]] = {}
    in_flight_by_group: dict[str, list[dict[str, Any]]] = {}
    stale_by_group: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        group_id = get_visibility_group(row.get("recurso", ""))
        if group_id:
            rows_by_group.setdefault(group_id, []).append(row)
    for row in window_rows:
        group_id = get_visibility_group(row.get("recurso", ""))
        if group_id:
            window_by_group.setdefault(group_id, []).append(row)
    for row in in_flight_rows or []:
        group_id = get_visibility_group(row.get("recurso", ""))
        if group_id:
            in_flight_by_group.setdefault(group_id, []).append(row)
    for row in stale_in_flight_rows or []:
        group_id = get_visibility_group(row.get("recurso", ""))
        if group_id:
            stale_by_group.setdefault(group_id, []).append(row)

    for group in groups:
        if not isinstance(group, dict):
            continue
        group_id = group.get("id")
        if not group_id:
            continue
        group_rows = rows_by_group.get(group_id, [])
        group["kpis"] = calculate_group_kpis(group_rows)
        group["tickets"] = group_ticket_scopes(
            group_rows,
            window_by_group.get(group_id, []),
            in_flight_rows=in_flight_by_group.get(group_id, []),
            stale_in_flight_rows=stale_by_group.get(group_id, []),
        )

    return contract
