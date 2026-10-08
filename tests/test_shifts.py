"""T18 — turnos por carril: loader, matcher y segmentos para el Timeline.

El carril se identifica por RECURSO ASIGNADO (nombre) y el JSON trae nombre
corto + codigo (ambiguo entre pools: AA existe dos veces). La correspondencia
es subconjunto de tokens acotado por familia, verificado 21/0 sobre datos
reales. Sin match no se inventa horario: el carril va normal + conteo.
"""
from __future__ import annotations

from datetime import datetime

from shifts import (
    WINDOW_MINUTES,
    clip_shifts_to_window,
    find_shifts_file,
    is_out_of_shift,
    load_shifts,
    match_person,
    normalize_person,
    off_shift_segments,
)

WSTART = datetime(2026, 10, 7, 20, 0)
WEND = datetime(2026, 10, 8, 4, 0)

PEOPLE = [
    {
        "code": "AA",
        "person": "Alvaro Auccapoma",
        "families": ("AgileOps ORO", "AgileOps Prod"),
        "shifts": [(datetime(2026, 10, 7, 20, 0), datetime(2026, 10, 8, 4, 0))],
    },
    {
        "code": "AA",
        "person": "Anthony Alcala",
        "families": ("Yape",),
        "shifts": [(datetime(2026, 10, 7, 8, 0), datetime(2026, 10, 7, 13, 0))],
    },
]


def test_normalize_folds_accents_case_and_dots():
    assert normalize_person("Álvaro  Auccapoma.") == ("alvaro", "auccapoma")
    assert normalize_person(None) == ()


def test_match_is_family_scoped_despite_code_collision():
    alvaro = match_person(
        "Alvaro Gonzalo Auccapoma Huanay", "AgileOps ORO", PEOPLE
    )
    assert alvaro is not None and alvaro["person"] == "Alvaro Auccapoma"
    anthony = match_person("Anthony Alcala Perez", "Yape", PEOPLE)
    assert anthony is not None and anthony["person"] == "Anthony Alcala"


def test_match_returns_none_when_ambiguous_or_missing():
    dupes = PEOPLE + [
        {
            "code": "AX",
            "person": "Alvaro Auccapoma",
            "families": ("AgileOps ORO",),
            "shifts": [],
        }
    ]
    assert (
        match_person("Alvaro Gonzalo Auccapoma Huanay", "AgileOps ORO", dupes)
        is None
    )
    assert (
        match_person("Alguien Desconocido", "AgileOps ORO", PEOPLE) is None
    )


def test_find_shifts_file_picks_newest_and_none_when_missing(tmp_path):
    old = tmp_path / "horarios_importados_2026_09.json"
    new = tmp_path / "horarios_importados_2026_10.json"
    old.write_text("{}", encoding="utf-8")
    new.write_text("{}", encoding="utf-8")
    import os

    os.utime(new, (old.stat().st_mtime + 5, old.stat().st_mtime + 5))
    assert find_shifts_file(tmp_path) == new
    assert find_shifts_file(tmp_path / "vacio") is None


def test_load_shifts_parses_sheet_structure(tmp_path):
    import json

    payload = {
        "pools": {
            "PoolSF": {
                "people": [
                    {
                        "code": "CM",
                        "person": "Carlos Medrano",
                        "shifts": [
                            {
                                "start": "2026-10-07T22:00",
                                "end": "2026-10-08T04:00",
                            }
                        ],
                    }
                ]
            }
        }
    }
    p = tmp_path / "horarios_importados_2026_10.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    loaded = load_shifts(p)
    assert loaded["people"][0]["families"] == ("S&F",)
    assert loaded["people"][0]["shifts"] == [
        (datetime(2026, 10, 7, 22, 0), datetime(2026, 10, 8, 4, 0))
    ]


def test_clip_handles_midnight_crossing_shift():
    shifts = [(datetime(2026, 10, 7, 20, 0), datetime(2026, 10, 8, 4, 0))]
    assert clip_shifts_to_window(shifts, WSTART, WEND) == [(0, 480)]


def test_clip_trims_to_window_edges():
    shifts = [(datetime(2026, 10, 7, 18, 0), datetime(2026, 10, 7, 22, 0))]
    assert clip_shifts_to_window(shifts, WSTART, WEND) == [(0, 120)]


def test_complement_marks_only_outside_as_fuera():
    assert off_shift_segments([(0, 480)]) == []
    assert off_shift_segments([]) == [(0, WINDOW_MINUTES)]
    assert off_shift_segments([(120, 300)]) == [(0, 120), (300, 480)]


def test_out_of_shift_needs_zero_overlap():
    assert (
        is_out_of_shift(
            datetime(2026, 10, 7, 18, 0),
            datetime(2026, 10, 7, 19, 0),
            [(datetime(2026, 10, 7, 20, 0), datetime(2026, 10, 8, 4, 0))],
        )
        is True
    )
    assert (
        is_out_of_shift(
            datetime(2026, 10, 7, 19, 0),
            datetime(2026, 10, 7, 21, 0),
            [(datetime(2026, 10, 7, 20, 0), datetime(2026, 10, 8, 4, 0))],
        )
        is False
    )
    assert is_out_of_shift(None, None, [],) is False


def _lane_row(ticket, recurso, responsable, ini, fin):
    return {
        "ticket": ticket,
        "nombre_app": "APP",
        "responsable": responsable,
        "recurso": recurso,
        "estado": "Coordinado",
        "inicio_impl": ini,
        "fin_impl": fin,
    }


def test_build_lane_payload_shades_only_outside():
    from shifts import build_lane_shifts

    rows = [
        _lane_row(
            "T1",
            "Pool AgileOps Prod",
            "Alvaro Gonzalo Auccapoma Huanay",
            datetime(2026, 10, 7, 23, 0),
            datetime(2026, 10, 8, 0, 30),
        )
    ]
    lanes = build_lane_shifts(rows, PEOPLE, WSTART, WEND)
    # Turno 20:00->04:00 cubre toda la ventana: sin fuera.
    lane = lanes["AgileOps Prod"]["Alvaro Gonzalo Auccapoma Huanay"]
    assert lane["matched"] is True
    assert lane["fuera"] == []


def test_build_lane_payload_marks_unmatched():
    from shifts import build_lane_shifts

    rows = [
        _lane_row(
            "T9",
            "Pool AgileOps Prod",
            "Angel Medina Cachay",
            datetime(2026, 10, 7, 23, 0),
            datetime(2026, 10, 8, 0, 30),
        )
    ]
    lanes = build_lane_shifts(rows, PEOPLE, WSTART, WEND)
    lane = lanes["AgileOps Prod"]["Angel Medina Cachay"]
    assert lane["matched"] is False
    assert lane["fuera"] == []


def test_collect_out_of_shift_flags_disjoint_only():
    from shifts import collect_out_of_shift

    rows = [
        _lane_row(
            "T-OK",
            "Pool AgileOps Prod",
            "Alvaro Gonzalo Auccapoma Huanay",
            datetime(2026, 10, 7, 23, 0),
            datetime(2026, 10, 8, 0, 30),
        ),
        _lane_row(
            "T-OUT",
            "Pool AgileOps Prod",
            "Alvaro Gonzalo Auccapoma Huanay",
            datetime(2026, 10, 7, 18, 0),
            datetime(2026, 10, 7, 19, 0),
        ),
    ]
    assert collect_out_of_shift(rows, PEOPLE) == ["T-OUT"]
