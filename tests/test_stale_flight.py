"""T6 — pases colgados: 'Pase en curso' con FIN IMPL ya pasado.

Son los tickets fantasma: el dash no los mostraba en ningun lado (ni
timeline, ni tabla, ni drawers) salvo que de casualidad tuvieran la
ratificacion vencida. Para un banco eso es ceguera, asi que tienen
indicador propio con drawer. Sin FIN valido no se juzga (no se puede
probar que este pasado).
"""
from __future__ import annotations

from datetime import datetime

from renderer import build_actions, filter_stale_in_flight, is_stale_in_flight

REF = datetime(2026, 10, 7, 17, 15)


def _row(ticket, estado="Pase en curso", ini=None, fin=None):
    return {
        "ticket": ticket,
        "nombre_app": "APP-" + ticket,
        "responsable": "Resp " + ticket,
        "estado": estado,
        "recurso": "Pool AgileOps Prod",
        "inicio_impl": ini,
        "fin_impl": fin,
    }


def test_en_curso_with_past_fin_is_stale():
    row = _row(
        "S1",
        ini=datetime(2026, 10, 7, 16, 0),
        fin=datetime(2026, 10, 7, 17, 0),
    )
    assert is_stale_in_flight(row, REF) is True


def test_en_curso_covering_now_is_not_stale():
    row = _row(
        "S2",
        ini=datetime(2026, 10, 7, 16, 0),
        fin=datetime(2026, 10, 7, 18, 0),
    )
    assert is_stale_in_flight(row, REF) is False


def test_en_curso_starting_in_future_is_not_stale():
    row = _row(
        "S3",
        ini=datetime(2026, 10, 7, 18, 0),
        fin=datetime(2026, 10, 7, 19, 0),
    )
    assert is_stale_in_flight(row, REF) is False


def test_other_states_with_past_fin_are_not_stale():
    row = _row(
        "S4",
        estado="Coordinado",
        ini=datetime(2026, 10, 7, 16, 0),
        fin=datetime(2026, 10, 7, 17, 0),
    )
    assert is_stale_in_flight(row, REF) is False


def test_missing_fin_is_not_stale():
    row = _row("S5", ini=datetime(2026, 10, 7, 16, 0), fin=None)
    assert is_stale_in_flight(row, REF) is False


def test_filter_keeps_only_stale():
    rows = [
        _row("K1", ini=datetime(2026, 10, 7, 16, 0), fin=datetime(2026, 10, 7, 17, 0)),
        _row("K2", ini=datetime(2026, 10, 7, 16, 0), fin=datetime(2026, 10, 7, 18, 0)),
        _row("K3", estado="Cerrado", ini=datetime(2026, 10, 7, 16, 0), fin=datetime(2026, 10, 7, 17, 0)),
    ]
    assert [r["ticket"] for r in filter_stale_in_flight(rows, REF)] == ["K1"]


def test_payload_defaults_to_empty():
    a = build_actions([], [])
    assert a["staleInFlight"] == []


def test_payload_maps_stale_records():
    row = _row(
        "V9",
        ini=datetime(2026, 10, 7, 16, 0),
        fin=datetime(2026, 10, 7, 17, 0),
    )
    a = build_actions([], [], stale_in_flight_rows=[row])
    assert [r["ticket"] for r in a["staleInFlight"]] == ["V9"]
    assert a["staleInFlight"][0]["finImpl"] == "07/10/2026 17:00"


def test_payload_keys_include_stale():
    a = build_actions([], [])
    assert set(a) == {
        "passesInWindow",
        "lateStarts",
        "ratificationsSoon",
        "ratificationsExpired",
        "inFlightNow",
        "staleInFlight",
    }


def test_group_scopes_include_stale():
    from kpi import group_ticket_scopes

    rows = [
        _row("G1", ini=datetime(2026, 10, 7, 16, 0), fin=datetime(2026, 10, 7, 17, 0)),
        _row("G2", ini=datetime(2026, 10, 7, 16, 0), fin=datetime(2026, 10, 7, 18, 0)),
    ]
    stale = filter_stale_in_flight(rows, REF)
    scopes = group_ticket_scopes(rows, [], stale_in_flight_rows=stale)
    assert scopes["staleInFlight"] == ["G1"]
