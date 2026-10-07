"""
T7 — pool visibility groups as a PRESENTATION LAYER (ADR-011).

The 4 pool families (Yape, S&F, AgileOps ORO, AgileOps Prod) are grouped into
3 visibility groups (YAPE, S&F, AgileOps) that the dashboard exposes through a
selector. The grouping sits ON TOP of the pool scope (ADR-009): it never widens
nor narrows inclusion, it only partitions what is already in scope.

These tests pin:

- the 3 groups and their declared order;
- each group's family list;
- the partition invariant: every pool family is in EXACTLY ONE group — no
  family orphaned (and therefore invisible in every group) and none duplicated;
- full coverage of the 8 in-scope RECURSO values;
- per-group KPIs next to the global KPI object (which must stay);
- that the two-family group (AgileOps) really aggregates across both families
  instead of reporting only one of them;
- that the projection is defensive: a malformed group table is a loud
  ValueError, never a silently dropped pool.
"""
from datetime import datetime, timedelta

import pytest

import column_map
from adapter import compute_window, to_contract
from column_map import (
    POOL_FAMILY_ORDER,
    _build_visibility_groups,
    get_pool_name,
    get_visibility_group,
    is_in_scope_pool,
    visibility_groups,
)
from kpi import update_contract_kpis, update_contract_visibility_kpis
from rules import apply_rules

# The 3 visibility groups, in the order the product owner declared them.
EXPECTED_GROUPS = [
    ("yape", "YAPE", ["Yape"]),
    ("sf", "S&F", ["S&F"]),
    ("agileops", "AgileOps", ["AgileOps ORO", "AgileOps Prod"]),
]

# The 8 in-scope RECURSO values, verbatim from the workbook (ADR-009).
IN_SCOPE = [
    "POOL - YAPE",
    "POOL - YAPE-DERIVADO",
    "Pool S&F",
    "POOL S&F-DERIVADO",
    "Pool AgileOps ORO",
    "Pool AgileOps ORO - Derivado",
    "Pool AgileOps Prod",
    "Pool AgileOps Prod - Derivado",
]

ANCHOR = datetime(2026, 9, 11, 9, 0)     # window start (floor of the reference)
# Rule reference (meta.updatedAt). Deliberately 40 min into the hour so the
# window is 09:00 -> 17:00 while rows that start at 09:10..09:25 are both
# INSIDE the window and already past the late-start threshold.
REFERENCE = datetime(2026, 9, 11, 9, 40)


def _row(ticket, recurso, inicio, fin, estado="Coordinado"):
    """One normalized row with the ratification dates that drive the rules."""
    return {
        "ticket": ticket,
        "nombre_app": f"APP-{ticket}",
        "responsable": "Ana Perez",
        "recurso": recurso,
        "estado": estado,
        "inicio_impl": inicio,
        "fin_impl": fin,
        # 20 min before the reference starts, 10 min after it ends -> expired.
        "inicio_rati": REFERENCE - timedelta(minutes=40),
        "fin_rati": REFERENCE - timedelta(minutes=10),
    }


def _contract_with_groups(rows, window_rows=None):
    """Build a contract and populate the per-visibility-group payloads.

    Mirrors main.main(): to_contract -> update_contract_kpis (global) ->
    update_contract_visibility_kpis (per group). The global KPI object is what
    to_contract leaves at zero, so it must be computed explicitly here too —
    otherwise every "global == sum of groups" assertion would pass vacuously.
    """
    window = compute_window(REFERENCE)
    annotated = apply_rules(rows, reference_now=REFERENCE)
    contract = to_contract(annotated, {}, window)
    contract = update_contract_kpis(contract, annotated)
    if window_rows is None:
        window_rows = annotated
    return update_contract_visibility_kpis(contract, annotated, window_rows)


def _group_by_id(contract, group_id):
    for group in contract["meta"]["visibilityGroups"]:
        if group["id"] == group_id:
            return group
    raise AssertionError(f"group {group_id!r} is not in the contract")


# ---------------------------------------------------------------
# The 3 groups and their order
# ---------------------------------------------------------------
def test_three_visibility_groups_in_declared_order():
    projected = visibility_groups()
    assert [(g["id"], g["label"], g["families"]) for g in projected] == EXPECTED_GROUPS


def test_group_ids_are_the_declaration_order():
    assert column_map.VISIBILITY_GROUP_IDS == ("yape", "sf", "agileops")


def test_each_group_family_list_is_correct():
    projected = {g["id"]: g for g in visibility_groups()}
    assert projected["yape"]["families"] == ["Yape"]
    assert projected["sf"]["families"] == ["S&F"]
    assert projected["agileops"]["families"] == ["AgileOps ORO", "AgileOps Prod"]


def test_first_group_is_the_default_candidate():
    """The dashboard defaults to the FIRST group (ADR-011)."""
    assert visibility_groups()[0]["id"] == "yape"


def test_group_projection_is_a_fresh_object_each_call():
    """A consumer mutating the projection must not corrupt module state."""
    first = visibility_groups()
    first[0]["families"].append("Injected")
    first[0]["id"] = "hacked"
    assert visibility_groups()[0]["id"] == "yape"
    assert visibility_groups()[0]["families"] == ["Yape"]


# ---------------------------------------------------------------
# The partition invariant — no orphan, no duplicate
# ---------------------------------------------------------------
def test_every_pool_family_belongs_to_exactly_one_group():
    seen: dict[str, list[str]] = {}
    for group in visibility_groups():
        for family in group["families"]:
            seen.setdefault(family, []).append(group["id"])

    assert sorted(seen) == sorted(POOL_FAMILY_ORDER), (
        f"orphaned or unknown families: {sorted(set(POOL_FAMILY_ORDER) - set(seen))}"
    )
    duplicated = {f: g for f, g in seen.items() if len(g) != 1}
    assert duplicated == {}, f"family in more than one group: {duplicated}"


def test_no_group_is_empty():
    for group in visibility_groups():
        assert group["families"], group["id"]


def test_group_ids_are_unique():
    ids = [g["id"] for g in visibility_groups()]
    assert len(ids) == len(set(ids))


def test_group_labels_are_unique():
    labels = [g["label"] for g in visibility_groups()]
    assert len(labels) == len(set(labels))


# ---------------------------------------------------------------
# RECURSO coverage — the 8 values, fully covered, no second list
# ---------------------------------------------------------------
def test_the_eight_in_scope_resources_are_fully_covered_by_the_groups():
    covered: list[str] = []
    for group in visibility_groups():
        covered.extend(group["resources"])
    assert set(covered) == set(IN_SCOPE)
    assert len(covered) == 8, "a RECURSO value is covered twice by the groups"


def test_every_in_scope_resource_resolves_to_a_visibility_group():
    for recurso in IN_SCOPE:
        group_id = get_visibility_group(recurso)
        assert group_id, f"{recurso!r} belongs to no visibility group"
        assert group_id in column_map.VISIBILITY_GROUP_IDS


def test_group_resources_are_derived_from_the_family_table_not_redeclared():
    """A group's resources come from the family table, per family name."""
    by_family = dict(column_map._POOL_FAMILY_RESOURCES)
    for group in visibility_groups():
        expected = [r for family in group["families"] for r in by_family[family]]
        assert group["resources"] == expected, group["id"]


def test_out_of_scope_resources_belong_to_no_group():
    """Grouping is a layer ON TOP of the whitelist, never a replacement."""
    for recurso in [
        "INFRAESTRUCTURA",
        "AUTOMATIZADO",
        "AUTOMATIZADO ITSM",
        "EXPRESS AUTOMATICO",
        "POOL AGILEOPS",
        "",
        None,
    ]:
        assert not is_in_scope_pool(recurso), recurso
        assert get_visibility_group(recurso) == "", recurso


def test_group_assignment_follows_family_resolution():
    expected = {
        "POOL - YAPE": "yape",
        "POOL - YAPE-DERIVADO": "yape",
        "Pool S&F": "sf",
        "POOL S&F-DERIVADO": "sf",
        "Pool AgileOps ORO": "agileops",
        "Pool AgileOps ORO - Derivado": "agileops",
        "Pool AgileOps Prod": "agileops",
        "Pool AgileOps Prod - Derivado": "agileops",
    }
    for recurso, group_id in expected.items():
        assert get_visibility_group(recurso) == group_id, recurso
        assert get_pool_name(recurso) in _group_by_id(
            {"meta": {"visibilityGroups": visibility_groups()}}, group_id
        )["families"]


# ---------------------------------------------------------------
# meta.visibilityGroups — emitted by Python
# ---------------------------------------------------------------
def test_contract_publishes_the_groups_under_meta():
    window = compute_window(REFERENCE)
    contract = to_contract([], {}, window)
    groups = contract["meta"]["visibilityGroups"]
    assert [(g["id"], g["label"]) for g in groups] == [("yape", "YAPE"),
                                                       ("sf", "S&F"),
                                                       ("agileops", "AgileOps")]


def test_contract_publishes_the_groups_with_zero_bars_in_the_window():
    window = compute_window(REFERENCE)
    contract = to_contract([], {}, window)
    assert contract["timeline"] == []
    assert len(contract["meta"]["visibilityGroups"]) == 3


def test_pool_order_is_untouched_by_the_grouping():
    """The 4 families and their display order are NOT collapsed into groups."""
    window = compute_window(REFERENCE)
    contract = to_contract([], {}, window)
    assert contract["meta"]["poolOrder"] == list(POOL_FAMILY_ORDER)


# ---------------------------------------------------------------
# Per-group KPIs — the aggregate counts of a hidden pool must not leak
# ---------------------------------------------------------------
def test_every_group_has_per_group_kpis_and_the_global_object_remains():
    rows = [
        _row("T-YAPE", "POOL - YAPE", ANCHOR + timedelta(minutes=10),
             ANCHOR + timedelta(minutes=40)),
        _row("T-SF", "Pool S&F", ANCHOR + timedelta(minutes=10),
             ANCHOR + timedelta(minutes=40)),
        _row("T-ORO", "Pool AgileOps ORO", ANCHOR + timedelta(minutes=10),
             ANCHOR + timedelta(minutes=40)),
        _row("T-PROD", "Pool AgileOps Prod", ANCHOR + timedelta(minutes=10),
             ANCHOR + timedelta(minutes=40)),
    ]
    contract = _contract_with_groups(rows)

    groups = contract["meta"]["visibilityGroups"]
    assert len(groups) == 3
    for group in groups:
        kpis = group["kpis"]
        assert set(kpis) == {
            "lateStarts",
            "ratificationsSoon",
            "ratificationsExpired",
            "reversions",
        }, group["id"]
        assert all(isinstance(v, int) for v in kpis.values()), group["id"]

    # The global KPI object is still present and unchanged in shape.
    assert set(contract["kpis"]) == {
        "lateStarts",
        "ratificationsSoon",
        "ratificationsExpired",
        "reversions",
    }


def test_global_kpis_are_the_sum_of_the_group_kpis():
    rows = [
        _row("T-YAPE", "POOL - YAPE", ANCHOR + timedelta(minutes=10),
             ANCHOR + timedelta(minutes=40)),
        _row("T-SF", "Pool S&F", ANCHOR + timedelta(minutes=15),
             ANCHOR + timedelta(minutes=45)),
        _row("T-ORO", "Pool AgileOps ORO", ANCHOR + timedelta(minutes=20),
             ANCHOR + timedelta(minutes=50)),
        _row("T-PROD", "Pool AgileOps Prod", ANCHOR + timedelta(minutes=25),
             ANCHOR + timedelta(minutes=55)),
    ]
    contract = _contract_with_groups(rows)
    groups = contract["meta"]["visibilityGroups"]

    assert contract["kpis"]["lateStarts"] == 4
    for key in ("lateStarts", "ratificationsSoon", "ratificationsExpired", "reversions"):
        assert sum(g["kpis"][key] for g in groups) == contract["kpis"][key], key


def test_per_group_kpis_do_not_count_another_groups_rows():
    rows = [
        _row("T-YAPE", "POOL - YAPE", ANCHOR + timedelta(minutes=10),
             ANCHOR + timedelta(minutes=40)),
        _row("T-ORO", "Pool AgileOps ORO", ANCHOR + timedelta(minutes=10),
             ANCHOR + timedelta(minutes=40)),
    ]
    contract = _contract_with_groups(rows)

    assert _group_by_id(contract, "yape")["kpis"]["lateStarts"] == 1
    assert _group_by_id(contract, "sf")["kpis"]["lateStarts"] == 0
    assert _group_by_id(contract, "agileops")["kpis"]["lateStarts"] == 1
    assert contract["kpis"]["lateStarts"] == 2


def test_two_family_group_aggregates_across_both_families():
    """AgileOps covers ORO + Prod: its KPI must be the SUM, not one of them."""
    rows = [
        _row("T-ORO-1", "Pool AgileOps ORO", ANCHOR + timedelta(minutes=10),
             ANCHOR + timedelta(minutes=40)),
        _row("T-ORO-2", "Pool AgileOps ORO - Derivado",
             ANCHOR + timedelta(minutes=15), ANCHOR + timedelta(minutes=45)),
        _row("T-PROD-1", "Pool AgileOps Prod", ANCHOR + timedelta(minutes=20),
             ANCHOR + timedelta(minutes=50)),
        _row("T-PROD-2", "Pool AgileOps Prod - Derivado",
             ANCHOR + timedelta(minutes=25), ANCHOR + timedelta(minutes=55)),
        _row("T-YAPE", "POOL - YAPE", ANCHOR + timedelta(minutes=10),
             ANCHOR + timedelta(minutes=40)),
    ]
    contract = _contract_with_groups(rows)

    oro_rows = [r for r in rows if "ORO" in r["recurso"]]
    prod_rows = [r for r in rows if "Prod" in r["recurso"]]
    oro_alone = _contract_with_groups(oro_rows)["kpis"]
    prod_alone = _contract_with_groups(prod_rows)["kpis"]

    group = _group_by_id(contract, "agileops")
    assert group["kpis"]["lateStarts"] == 4
    assert group["kpis"]["ratificationsExpired"] == 4
    # The group total is strictly greater than either family alone: it really
    # aggregates, it does not report a single family.
    assert group["kpis"]["lateStarts"] > oro_alone["lateStarts"]
    assert group["kpis"]["lateStarts"] > prod_alone["lateStarts"]
    assert group["kpis"]["lateStarts"] == oro_alone["lateStarts"] + prod_alone["lateStarts"]
    # And the other groups are unaffected by the two AgileOps families.
    assert _group_by_id(contract, "yape")["kpis"]["lateStarts"] == 1
    assert _group_by_id(contract, "sf")["kpis"]["lateStarts"] == 0


def test_group_kpis_are_zero_for_a_group_with_no_rows():
    contract = _contract_with_groups([])
    for group in contract["meta"]["visibilityGroups"]:
        assert group["kpis"] == {
            "lateStarts": 0,
            "ratificationsSoon": 0,
            "ratificationsExpired": 0,
            "reversions": 0,
        }


# ---------------------------------------------------------------
# Per-group action ticket sets — the drawer must be filterable too
# ---------------------------------------------------------------
def test_each_group_publishes_the_four_action_ticket_sets():
    contract = _contract_with_groups([])
    for group in contract["meta"]["visibilityGroups"]:
        assert set(group["tickets"]) == {
            "passesInWindow",
            "lateStarts",
            "ratificationsSoon",
            "ratificationsExpired",
            "inFlightNow",
        }, group["id"]


def test_action_ticket_sets_partition_the_window_passes():
    in_window = [
        _row("T-YAPE", "POOL - YAPE", ANCHOR + timedelta(minutes=10),
             ANCHOR + timedelta(minutes=40)),
        _row("T-SF", "Pool S&F", ANCHOR + timedelta(minutes=15),
             ANCHOR + timedelta(minutes=45)),
        _row("T-ORO", "Pool AgileOps ORO", ANCHOR + timedelta(minutes=20),
             ANCHOR + timedelta(minutes=50)),
        _row("T-PROD", "Pool AgileOps Prod", ANCHOR + timedelta(minutes=25),
             ANCHOR + timedelta(minutes=55)),
    ]
    # Outside the 09:00 -> 17:00 window: must not appear in any window scope.
    out_of_window = [
        _row("T-OUT", "Pool AgileOps Prod", ANCHOR + timedelta(hours=9),
             ANCHOR + timedelta(hours=10)),
    ]
    contract = _contract_with_groups(in_window + out_of_window, window_rows=in_window)
    groups = contract["meta"]["visibilityGroups"]

    union: set[str] = set()
    for group in groups:
        union |= set(group["tickets"]["passesInWindow"])
    assert union == {"T-YAPE", "T-SF", "T-ORO", "T-PROD"}

    assert _group_by_id(contract, "yape")["tickets"]["passesInWindow"] == ["T-YAPE"]
    assert _group_by_id(contract, "sf")["tickets"]["passesInWindow"] == ["T-SF"]
    assert _group_by_id(contract, "agileops")["tickets"]["passesInWindow"] == [
        "T-ORO",
        "T-PROD",
    ]


def test_late_start_ticket_sets_partition_the_late_start_kpi():
    rows = [
        _row("T-YAPE", "POOL - YAPE", ANCHOR + timedelta(minutes=10),
             ANCHOR + timedelta(minutes=40)),
        _row("T-ORO", "Pool AgileOps ORO", ANCHOR + timedelta(minutes=10),
             ANCHOR + timedelta(minutes=40)),
        _row("T-PROD", "Pool AgileOps Prod", ANCHOR + timedelta(minutes=10),
             ANCHOR + timedelta(minutes=40)),
    ]
    contract = _contract_with_groups(rows)

    assert _group_by_id(contract, "yape")["tickets"]["lateStarts"] == ["T-YAPE"]
    assert _group_by_id(contract, "agileops")["tickets"]["lateStarts"] == [
        "T-ORO",
        "T-PROD",
    ]
    assert _group_by_id(contract, "sf")["tickets"]["lateStarts"] == []
    assert contract["kpis"]["lateStarts"] == 3


def test_terminal_rows_never_reach_any_group_ticket_set():
    """ADR-006 still holds inside a group."""
    rows = [
        _row("T-YAPE", "POOL - YAPE", ANCHOR + timedelta(minutes=10),
             ANCHOR + timedelta(minutes=40)),
        _row("T-YAPE-DONE", "POOL - YAPE", ANCHOR + timedelta(minutes=10),
             ANCHOR + timedelta(minutes=40), estado="Terminado Satisfactorio"),
    ]
    contract = _contract_with_groups(rows)
    group = _group_by_id(contract, "yape")
    assert group["kpis"]["lateStarts"] == 1
    assert group["tickets"]["lateStarts"] == ["T-YAPE"]


# ---------------------------------------------------------------
# Defensive projection — a malformed group table must be loud
# ---------------------------------------------------------------
def test_projection_rejects_an_orphaned_family():
    bad = (
        ("yape", "YAPE", ("Yape",)),
        ("sf", "S&F", ("S&F",)),
        ("agileops", "AgileOps", ("AgileOps ORO",)),  # Prod left out
    )
    with pytest.raises(ValueError, match="AgileOps Prod"):
        _build_visibility_groups(POOL_FAMILY_ORDER, bad)


def test_projection_rejects_a_duplicated_family():
    bad = (
        ("yape", "YAPE", ("Yape", "AgileOps Prod")),
        ("sf", "S&F", ("S&F",)),
        ("agileops", "AgileOps", ("AgileOps ORO", "AgileOps Prod")),
    )
    with pytest.raises(ValueError, match="AgileOps Prod"):
        _build_visibility_groups(POOL_FAMILY_ORDER, bad)


def test_projection_rejects_an_unknown_family():
    bad = (
        ("yape", "YAPE", ("Yape", "Pool Legacy")),
        ("sf", "S&F", ("S&F",)),
        ("agileops", "AgileOps", ("AgileOps ORO", "AgileOps Prod")),
    )
    with pytest.raises(ValueError, match="Pool Legacy"):
        _build_visibility_groups(POOL_FAMILY_ORDER, bad)


def test_projection_rejects_a_duplicated_group_id():
    bad = (
        ("yape", "YAPE", ("Yape",)),
        ("yape", "S&F", ("S&F",)),
        ("agileops", "AgileOps", ("AgileOps ORO", "AgileOps Prod")),
    )
    with pytest.raises(ValueError, match="yape"):
        _build_visibility_groups(POOL_FAMILY_ORDER, bad)


def test_projection_rejects_an_empty_group():
    bad = (
        ("yape", "YAPE", ("Yape",)),
        ("sf", "S&F", ("S&F",)),
        ("agileops", "AgileOps", ()),
    )
    with pytest.raises(ValueError):
        _build_visibility_groups(POOL_FAMILY_ORDER, bad)