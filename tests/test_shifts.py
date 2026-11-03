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


# --- Esquema flat del export del cliente (noviembre 2026 en adelante) ---

FLAT_PAYLOAD = {
    "generated_at": "2026-11-02T17:31:23",
    "people": [
        {
            "resource": "Pool de pases",
            "person": "Cesar Pingo",
            "hoja": "PoolPases",
            "tipoHorario": "Normal",
            "fecha": "2026-11-01",
            "shifts": [
                {"start": "2026-11-07T22:00", "end": "2026-11-08T01:00"}
            ],
        },
        {
            "resource": "Pool de pases",
            "person": "Cesar Pingo",
            "hoja": "PoolPases-D",
            "tipoHorario": "Derivado",
            "fecha": "2026-11-01",
            "shifts": [
                {"start": "2026-11-07T22:00", "end": "2026-11-08T00:00"},
                {"start": "2026-11-08T02:00", "end": "2026-11-08T04:00"},
            ],
        },
        {
            "resource": "PoolCapacity",
            "person": "Ana Aguilera",
            "hoja": "PoolCapacity",
            "tipoHorario": "Normal",
            "fecha": "2026-11-02",
            "shifts": [{"start": "2026-11-07T20:00", "end": "2026-11-08T04:00"}],
        },
        {
            "resource": "Samay02",
            "person": "Juan Externo",
            "hoja": "Samay2",
            "tipoHorario": "Normal",
            "fecha": "2026-11-02",
            "shifts": [{"start": "2026-11-07T22:00", "end": "2026-11-08T04:00"}],
        },
        {
            "resource": "Proyectos",
            "person": "Grupo Proyecto",
            "hoja": "PoolProyecto",
            "tipoHorario": "Normal",
            "fecha": "2026-11-02",
            "shifts": [{"start": "2026-11-07T22:00", "end": "2026-11-08T04:00"}],
        },
    ],
}


def _write_flat(tmp_path):
    import json

    p = tmp_path / "horarios_importados_2026_11.json"
    p.write_text(json.dumps(FLAT_PAYLOAD), encoding="utf-8")
    return p


def test_load_flat_merges_same_person_tracks_and_filters_excluded_sheets(tmp_path):
    loaded = load_shifts(_write_flat(tmp_path))
    by_name = {p["person"]: p for p in loaded["people"]}
    # Las hojas que no hacen pases no entran.
    assert set(by_name) == {"Cesar Pingo", "Ana Aguilera"}
    cesar = by_name["Cesar Pingo"]
    # La misma persona en PoolPases y PoolPases-D es UN candidato con dos pistas.
    assert cesar["families"] == ("AgileOps ORO", "AgileOps Prod")
    assert cesar["tracks"]["normal"] == [
        (datetime(2026, 11, 7, 22, 0), datetime(2026, 11, 8, 1, 0))
    ]
    assert cesar["tracks"]["derivado"] == [
        (datetime(2026, 11, 7, 22, 0), datetime(2026, 11, 8, 0, 0)),
        (datetime(2026, 11, 8, 2, 0), datetime(2026, 11, 8, 4, 0)),
    ]


def test_load_flat_capacity_covers_every_pool_family(tmp_path):
    loaded = load_shifts(_write_flat(tmp_path))
    ana = next(p for p in loaded["people"] if p["person"] == "Ana Aguilera")
    assert ana["families"] == ("Yape", "S&F", "AgileOps ORO", "AgileOps Prod")


def test_match_flat_returns_availability_union(tmp_path):
    loaded = load_shifts(_write_flat(tmp_path))
    people = loaded["people"]
    cesar = match_person("Cesar Andres Pingo Ruiz", "AgileOps Prod", people)
    # Union de sus pistas normal + derivado, fusionadas por solapamiento.
    assert cesar is not None and cesar["shifts"] == [
        (datetime(2026, 11, 7, 22, 0), datetime(2026, 11, 8, 1, 0)),
        (datetime(2026, 11, 8, 2, 0), datetime(2026, 11, 8, 4, 0)),
    ]
    # PoolCapacity no tiene pista derivada: su pista normal no cambia.
    ana = match_person(
        "Ana Maria Aguilera Ferrer", "S&F", people, track="derivado"
    )
    assert ana is not None and ana["shifts"] == [
        (datetime(2026, 11, 7, 20, 0), datetime(2026, 11, 8, 4, 0))
    ]


def test_lane_payload_shades_with_union_of_tracks_regardless_of_bar_type():
    from shifts import build_lane_shifts

    people = [
        {
            "person": "Cesar Pingo",
            "families": ("AgileOps Prod",),
            "shifts_by_track": {
                "normal": [
                    (
                        datetime(2026, 10, 7, 22, 0),
                        datetime(2026, 10, 8, 1, 0),
                    )
                ],
                "derivado": [
                    (
                        datetime(2026, 10, 7, 22, 0),
                        datetime(2026, 10, 8, 0, 0),
                    ),
                    (
                        datetime(2026, 10, 8, 2, 0),
                        datetime(2026, 10, 8, 4, 0),
                    ),
                ],
            },
        }
    ]
    derivado_row = _lane_row(
        "T1",
        "Pool AgileOps Prod - Derivado",
        "Cesar Andres Pingo Ruiz",
        datetime(2026, 10, 7, 23, 0),
        datetime(2026, 10, 8, 0, 30),
    )
    normal_row = _lane_row(
        "T2",
        "Pool AgileOps Prod",
        "Cesar Andres Pingo Ruiz",
        datetime(2026, 10, 7, 23, 0),
        datetime(2026, 10, 8, 0, 30),
    )
    # Ambos tipos de barra se sombrean con la MISMA disponibilidad.
    for row in (derivado_row, normal_row):
        lanes = build_lane_shifts([row], people, WSTART, WEND)
        lane = lanes["AgileOps Prod"]["Cesar Andres Pingo Ruiz"]
        assert lane["matched"] is True
        # Pistas unidas: cubre 22:00-01:00 y 02:00-04:00 dentro de la ventana
        # 20:00-04:00; solo quedan fuera 20:00-22:00 y 01:00-02:00.
        assert lane["fuera"] == [[0, 120], [300, 360]]


def test_collect_out_of_shift_ignores_bar_type():
    from shifts import collect_out_of_shift

    people = [
        {
            "person": "Cesar Pingo",
            "families": ("AgileOps Prod",),
            "shifts_by_track": {
                "normal": [
                    (
                        datetime(2026, 10, 7, 22, 0),
                        datetime(2026, 10, 8, 6, 0),
                    )
                ],
                "derivado": [
                    (
                        datetime(2026, 10, 7, 22, 0),
                        datetime(2026, 10, 8, 0, 0),
                    ),
                ],
            },
        }
    ]
    rows = [
        # Pase derivado 23:00-00:30: dentro de su turno unificado.
        _lane_row(
            "T-D-OK",
            "Pool AgileOps Prod - Derivado",
            "Cesar Andres Pingo Ruiz",
            datetime(2026, 10, 7, 23, 0),
            datetime(2026, 10, 8, 0, 30),
        ),
        # Pase derivado 04:30-05:30: la pista derivada no lo cubre (termina
        # 00:00), pero la NORMAL (22:00-06:00) si. Union manda: no es anomalia.
        _lane_row(
            "T-D-OK2",
            "Pool AgileOps Prod - Derivado",
            "Cesar Andres Pingo Ruiz",
            datetime(2026, 10, 8, 4, 30),
            datetime(2026, 10, 8, 5, 30),
        ),
        # 07:00-08:00 esta fuera de todo horario: ese si se marca.
        _lane_row(
            "T-OUT",
            "Pool AgileOps Prod - Derivado",
            "Cesar Andres Pingo Ruiz",
            datetime(2026, 10, 8, 7, 0),
            datetime(2026, 10, 8, 8, 0),
        ),
    ]
    assert collect_out_of_shift(rows, people) == ["T-OUT"]


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
