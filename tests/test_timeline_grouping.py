"""
Tests for the Timeline semantics.

- The Data Contract keeps `pool` as the display POOL FAMILY (Yape, S&F,
  AgileOps ORO, AgileOps Prod), resolved from the real RECURSO value.
- Groups are emitted in the canonical display order, which is also published
  as meta.poolOrder so the web layer stops hardcoding it.
- The responsable grouping is render-only (frontend, from window.ChangeOpsActions).
- Bar `name` carries NOMBRE APP; the visible bar label is the ticket (frontend).
"""
from datetime import datetime

from adapter import compute_window, to_contract
from column_map import POOL_FAMILY_ORDER


def _row(ticket, resp, hour, app="APP", recurso="Pool AgileOps Prod"):
    return {
        "ticket": ticket,
        "nombre_app": app,
        "responsable": resp,
        "recurso": recurso,
        "estado": "Coordinado",
        "inicio_impl": datetime(2026, 9, 11, hour, 0),
        "fin_impl": datetime(2026, 9, 11, hour + 1, 0),
    }


def test_timeline_grouped_by_pool_not_responsable():
    """The contract groups by the display pool family, never by responsable."""
    rows = [
        _row("T1", "Ana", 9, recurso="POOL - YAPE"),
        _row("T2", "Beto", 10, recurso="Pool S&F"),
    ]
    window = compute_window(datetime(2026, 9, 11, 8, 30))
    contract = to_contract(rows, {}, window)

    groups = [g["pool"] for g in contract["timeline"]]
    assert groups == ["Yape", "S&F"]
    # the responsable never leaks into the contract group key
    assert "Ana" not in groups and "Beto" not in groups


def test_timeline_group_order_is_display_order():
    """All 5 families render in the canonical display order, not alphabetical."""
    rows = [
        _row("T-prod", "Ana", 9, recurso="Pool AgileOps Prod - Derivado"),
        _row("T-sf", "Beto", 10, recurso="POOL S&F-DERIVADO"),
        _row("T-oro", "Caro", 11, recurso="Pool AgileOps ORO"),
        _row("T-oro-der", "Elena", 12, recurso="Pool AgileOps ORO - Derivado"),
        _row("T-yape", "Dani", 13, recurso="POOL - YAPE-DERIVADO"),
    ]
    window = compute_window(datetime(2026, 9, 11, 8, 30))
    contract = to_contract(rows, {}, window)

    assert [g["pool"] for g in contract["timeline"]] == [
        "Yape", "S&F", "AgileOps ORO", "AgileOps ORO Derivado", "AgileOps Prod",
    ]
    assert contract["meta"]["poolOrder"] == list(POOL_FAMILY_ORDER)


def test_pool_semantics_preserved():
    rows = [_row("T1", "Ana", 9, recurso="Pool AgileOps Prod")]
    window = compute_window(datetime(2026, 9, 11, 8, 30))
    contract = to_contract(rows, {}, window)
    assert contract["timeline"][0]["pool"] == "AgileOps Prod"


def test_bar_name_is_nombre_app():
    rows = [_row("T1", "Ana", 9, app="ANX5")]
    window = compute_window(datetime(2026, 9, 11, 8, 30))
    contract = to_contract(rows, {}, window)
    assert contract["timeline"][0]["bars"][0]["name"] == "ANX5"


def test_bar_keeps_ticket_and_times():
    rows = [_row("MVPAGIPRD-250870", "Ana", 9)]
    window = compute_window(datetime(2026, 9, 11, 8, 30))
    contract = to_contract(rows, {}, window)
    bar = contract["timeline"][0]["bars"][0]
    assert bar["ticket"] == "MVPAGIPRD-250870"
    assert bar["start"] == 60        # 09:00 - 08:00
    assert bar["duration"] == 60


def _raw(ticket, estado, hour, recurso="Pool AgileOps Prod"):
    return {
        "ticket": ticket,
        "nombre_app": "APP",
        "responsable": "R",
        "recurso": recurso,
        "estado": estado,
        "inicio_impl": datetime(2026, 9, 11, hour, 0),
        "fin_impl": datetime(2026, 9, 11, hour + 1, 0),
    }


def test_is_timeline_state():
    from adapter import is_timeline_state
    assert is_timeline_state("Coordinado")
    assert is_timeline_state("Pase en curso")
    for estado in [
        "Terminado Satisfactorio", "Cerrado", "Rechazado", "Pre Registrado",
        "Registrado", "Aprobado LT", "Aprobado CL QA", "Aprobado CL DEV",
        "Aprobado PO", "Aprobado Ops", "Ratificación Total Satisfactorio",
    ]:
        assert not is_timeline_state(estado), estado


def test_timeline_only_active_states():
    rows = [
        _raw("A", "Coordinado", 9),
        _raw("B", "Pase en curso", 10),
        _raw("C", "Terminado Satisfactorio", 9),   # excluded
        _raw("D", "Cerrado", 10),                  # excluded
        _raw("E", "Registrado", 10),               # excluded
    ]
    window = compute_window(datetime(2026, 9, 11, 8, 30))
    contract = to_contract(rows, {}, window)

    tickets = [b["ticket"] for g in contract["timeline"] for b in g["bars"]]
    assert set(tickets) == {"A", "B"}


if __name__ == "__main__":
    test_timeline_grouped_by_pool_not_responsable()
    test_timeline_group_order_is_display_order()
    test_pool_semantics_preserved()
    test_bar_name_is_nombre_app()
    test_bar_keeps_ticket_and_times()
    print("All timeline-semantics tests passed!")