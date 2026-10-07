"""T5 — pases en vuelo: estado 'Pase en curso' con INI <= ahora <= FIN.

El KPI 'Pases en ventana' contaba inicios dentro de la ventana (la mayoria
a futuro). El cliente quiere ver lo que se esta EJECUTANDO ahora, sacado
de la tabla operativa: es el mismo universo de la tabla (whitelist +
estados activos + trabajo vivo) restringido a estado en curso ya iniciado.
"""
from __future__ import annotations

from datetime import datetime

from renderer import build_actions, filter_in_flight, is_in_flight_now

REF = datetime(2026, 10, 6, 16, 30)

_MISSING = object()


def _row(ticket, estado="Pase en curso", ini=_MISSING, fin=_MISSING):
    return {
        "ticket": ticket,
        "nombre_app": "APP-" + ticket,
        "responsable": "Resp " + ticket,
        "estado": estado,
        "recurso": "Pool AgileOps Prod",
        "inicio_impl": datetime(2026, 10, 6, 16, 0) if ini is _MISSING else ini,
        "fin_impl": datetime(2026, 10, 6, 18, 0) if fin is _MISSING else fin,
    }


def test_en_curso_covering_now_counts():
    assert is_in_flight_now(_row("T1"), REF) is True


def test_en_curso_starting_in_future_does_not_count():
    row = _row(
        "T2",
        ini=datetime(2026, 10, 6, 17, 0),
        fin=datetime(2026, 10, 6, 19, 0),
    )
    assert is_in_flight_now(row, REF) is False


def test_en_curso_already_finished_does_not_count():
    row = _row(
        "T3",
        ini=datetime(2026, 10, 6, 14, 0),
        fin=datetime(2026, 10, 6, 16, 0),
    )
    assert is_in_flight_now(row, REF) is False


def test_coordinado_covering_now_does_not_count():
    assert is_in_flight_now(_row("T4", estado="Coordinado"), REF) is False


def test_terminal_covering_now_does_not_count():
    assert is_in_flight_now(_row("T5", estado="Cerrado"), REF) is False


def test_missing_dates_do_not_count():
    assert is_in_flight_now(_row("T6", ini=None, fin=None), REF) is False


def test_filter_keeps_only_in_flight():
    rows = [
        _row("F1"),
        _row("F2", estado="Coordinado"),
        _row("F3", ini=datetime(2026, 10, 6, 17, 0)),
    ]
    assert [r["ticket"] for r in filter_in_flight(rows, REF)] == ["F1"]


def test_payload_defaults_to_empty_without_table_rows():
    a = build_actions([], [])
    assert a["inFlightNow"] == []


def test_payload_maps_in_flight_records():
    a = build_actions([], [], in_flight_rows=[_row("V1")])
    assert [r["ticket"] for r in a["inFlightNow"]] == ["V1"]
    assert a["inFlightNow"][0]["iniImpl"] == "06/10/2026 16:00"
    assert a["inFlightNow"][0]["finImpl"] == "06/10/2026 18:00"


def test_payload_keys_include_in_flight():
    a = build_actions([], [])
    assert set(a) == {
        "passesInWindow",
        "lateStarts",
        "ratificationsSoon",
        "ratificationsExpired",
        "inFlightNow",
        "staleInFlight",
    }


def test_group_scopes_include_in_flight():
    from kpi import group_ticket_scopes

    rows = [_row("G1"), _row("G2", estado="Coordinado")]
    in_flight = filter_in_flight(rows, REF)
    scopes = group_ticket_scopes(rows, [], in_flight_rows=in_flight)
    assert scopes["inFlightNow"] == ["G1"]
