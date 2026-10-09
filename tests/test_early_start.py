"""T20 — pases adelantados: 'Pase en curso' con INICIO futuro.

Caso real OCD-231277: el especialista leyo mal la fecha y lo ejecuto antes
de su slot (01:00). Un en curso que todavia no debio empezar solo puede ser
adelanto o estado mal cargado: en ambos casos hay que verlo. Indicador
propio con tarjeta + drawer, mismo patron que colgados (T6).
"""
from __future__ import annotations

from datetime import datetime

from renderer import build_actions, filter_early_start, is_early_start

REF = datetime(2026, 10, 7, 23, 56)


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


def test_en_curso_starting_in_future_is_early():
    row = _row(
        "E1",
        ini=datetime(2026, 10, 8, 1, 0),
        fin=datetime(2026, 10, 8, 2, 0),
    )
    assert is_early_start(row, REF) is True


def test_en_curso_covering_now_is_not_early():
    row = _row(
        "E2",
        ini=datetime(2026, 10, 7, 23, 0),
        fin=datetime(2026, 10, 8, 1, 0),
    )
    assert is_early_start(row, REF) is False


def test_en_curso_with_past_fin_is_not_early():
    row = _row(
        "E3",
        ini=datetime(2026, 10, 7, 21, 0),
        fin=datetime(2026, 10, 7, 22, 0),
    )
    assert is_early_start(row, REF) is False


def test_other_states_starting_in_future_are_not_early():
    row = _row(
        "E4",
        estado="Coordinado",
        ini=datetime(2026, 10, 8, 1, 0),
        fin=datetime(2026, 10, 8, 2, 0),
    )
    assert is_early_start(row, REF) is False


def test_missing_inicio_is_not_early():
    row = _row("E5", ini=None, fin=datetime(2026, 10, 8, 2, 0))
    assert is_early_start(row, REF) is False


def test_filter_keeps_only_early():
    rows = [
        _row("K1", ini=datetime(2026, 10, 8, 1, 0), fin=datetime(2026, 10, 8, 2, 0)),
        _row("K2", ini=datetime(2026, 10, 7, 23, 0), fin=datetime(2026, 10, 8, 1, 0)),
        _row("K3", estado="Cerrado", ini=datetime(2026, 10, 8, 1, 0), fin=datetime(2026, 10, 8, 2, 0)),
    ]
    assert [r["ticket"] for r in filter_early_start(rows, REF)] == ["K1"]


def test_payload_defaults_to_empty():
    a = build_actions([], [])
    assert a["earlyStart"] == []


def test_payload_maps_early_records():
    row = _row(
        "V7",
        ini=datetime(2026, 10, 8, 1, 0),
        fin=datetime(2026, 10, 8, 2, 0),
    )
    a = build_actions([], [], early_start_rows=[row])
    assert [r["ticket"] for r in a["earlyStart"]] == ["V7"]
    assert a["earlyStart"][0]["iniImpl"] == "08/10/2026 01:00"


def test_payload_keys_include_early():
    a = build_actions([], [])
    assert set(a) == {
        "passesInWindow",
        "lateStarts",
        "ratificationsSoon",
        "ratificationsExpired",
        "inFlightNow",
        "staleInFlight",
        "earlyStart",
    }


def test_group_scopes_include_early():
    from kpi import group_ticket_scopes

    rows = [
        _row("G1", ini=datetime(2026, 10, 8, 1, 0), fin=datetime(2026, 10, 8, 2, 0)),
        _row("G2", ini=datetime(2026, 10, 7, 23, 0), fin=datetime(2026, 10, 8, 1, 0)),
    ]
    early = filter_early_start(rows, REF)
    scopes = group_ticket_scopes(rows, [], early_start_rows=early)
    assert scopes["earlyStart"] == ["G1"]
