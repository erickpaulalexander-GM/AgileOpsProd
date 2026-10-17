"""
Regression: duplicate ticket (impl + derivado) keeps its own timeline lane.

Case MVPLEGBCP-251934: the same ticket has an 11:00 implementation row
(Ronald) and a 15:00 derivado row (Cesar). Bars must carry their own
responsable so the frontend never collapses both into one lane via a
ticket-keyed lookup (which faked a conflict on Cesar's lane).
"""
from datetime import datetime

from adapter import compute_window, to_contract


def _row(ticket, responsable, recurso, h0, h1, day=(2026, 10, 16)):
    return {
        "ticket": ticket,
        "nombre_app": "CSCO",
        "responsable": responsable,
        "recurso": recurso,
        "estado": "Coordinado",
        "inicio_impl": datetime(*day, h0, 0),
        "fin_impl": datetime(*day, h1, 0),
    }


def test_duplicate_ticket_bars_keep_own_responsable():
    rows = [
        _row(
            "MVPLEGBCP-251934",
            "Ronald Romario Rubina Arias",
            "Pool AgileOps Prod",
            11,
            12,
        ),
        _row(
            "MVPLEGBCP-251934",
            "Cesar Augusto Huaman Huallparimachi",
            "Pool AgileOps Prod - Derivado",
            15,
            16,
        ),
    ]
    window = compute_window(datetime(2026, 10, 16, 10, 51, 56))
    contract = to_contract(rows, {}, window)

    bars = contract["timeline"][0]["bars"]
    assert len(bars) == 2
    by_start = {b["start"]: b for b in bars}
    assert by_start[60]["responsable"] == "Ronald Romario Rubina Arias"
    assert by_start[60]["type"] == "implementacion"
    assert by_start[300]["responsable"] == "Cesar Augusto Huaman Huallparimachi"
    assert by_start[300]["type"] == "derivado"


def test_single_ticket_bar_still_carries_ticket_and_times():
    rows = [
        _row("T1", "Ana", "Pool AgileOps Prod", 9, 10, day=(2026, 9, 11)),
    ]
    window = compute_window(datetime(2026, 9, 11, 8, 30))
    contract = to_contract(rows, {}, window)

    bar = contract["timeline"][0]["bars"][0]
    assert bar["ticket"] == "T1"
    assert bar["start"] == 60
    assert bar["duration"] == 60
    assert bar["responsable"] == "Ana"
