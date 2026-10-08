"""T14 — el Timeline muestra en vuelo que arranco antes de la ventana.

Objetivo: ver ocupacion de carril AHORA. Una barra iniciada fuera de la
ventana pero viva al abrir el dash se dibuja recortada al borde (start 0
y duracion visible). Sin FIN valido no se prueba solape: afuera, como
siempre. Solo geometria: reglas, KPIs y tabla no se tocan.
"""
from __future__ import annotations

from datetime import datetime

from adapter import compute_window, filter_to_window, to_contract

ANCHOR = datetime(2026, 10, 7, 20, 15)  # ventana 20:00 -> 04:00
WINDOW = compute_window(ANCHOR)


def _row(ticket, recurso, inicio, fin, estado="Pase en curso"):
    return {
        "ticket": ticket,
        "nombre_app": "APP-" + ticket,
        "responsable": "Ana Perez",
        "recurso": recurso,
        "estado": estado,
        "inicio_impl": inicio,
        "fin_impl": fin,
    }


def _bars(rows):
    return {
        b["ticket"]: b
        for p in to_contract(rows, {}, WINDOW)["timeline"]
        for b in p["bars"]
    }


def test_started_before_window_but_alive_is_drawn_clipped():
    rows = [
        _row(
            "T-CLIP",
            "Pool AgileOps Prod",
            datetime(2026, 10, 7, 19, 0),
            datetime(2026, 10, 7, 22, 0),
        )
    ]
    kept, dropped = filter_to_window(rows, WINDOW)
    assert len(kept) == 1 and dropped == 0
    bar = _bars(rows)["T-CLIP"]
    assert bar["start"] == 0
    assert bar["duration"] == 120


def test_spanning_row_covers_the_whole_grid():
    rows = [
        _row(
            "T-SPAN",
            "Pool AgileOps Prod",
            datetime(2026, 10, 7, 18, 0),
            datetime(2026, 10, 8, 6, 0),
        )
    ]
    bar = _bars(rows)["T-SPAN"]
    assert (bar["start"], bar["duration"]) == (0, 480)


def test_finished_before_window_stays_out():
    rows = [
        _row(
            "T-OLD",
            "Pool AgileOps Prod",
            datetime(2026, 10, 7, 18, 0),
            datetime(2026, 10, 7, 20, 0),
        )
    ]
    kept, dropped = filter_to_window(rows, WINDOW)
    assert kept == [] and dropped == 1
    assert "T-OLD" not in _bars(rows)


def test_missing_fin_cannot_prove_overlap():
    rows = [_row("T-NOFIN", "Pool AgileOps Prod",
                 datetime(2026, 10, 7, 19, 0), None)]
    kept, _ = filter_to_window(rows, WINDOW)
    assert kept == []


def test_in_window_start_keeps_exact_geometry():
    rows = [
        _row(
            "T-IN",
            "Pool AgileOps Prod",
            datetime(2026, 10, 7, 21, 0),
            datetime(2026, 10, 7, 22, 30),
        )
    ]
    bar = _bars(rows)["T-IN"]
    assert (bar["start"], bar["duration"]) == (60, 90)


def test_future_start_stays_out():
    rows = [
        _row(
            "T-FUT",
            "Pool AgileOps Prod",
            datetime(2026, 10, 8, 5, 0),
            datetime(2026, 10, 8, 6, 0),
        )
    ]
    kept, dropped = filter_to_window(rows, WINDOW)
    assert kept == [] and dropped == 1
