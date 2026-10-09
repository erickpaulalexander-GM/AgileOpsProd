"""Shifts loader: turnos por recurso para sombrear carriles fuera de turno.

Fuente: ``horarios_importados_YYYY_MM.json`` en el input dir (patron por
config, el mas nuevo manda). Estructura: pools (sheets) -> people (code,
person, shifts con start/end ISO). Los calendarios traen datetimes
absolutas, asi el cruce de medianoche sale solo.

Matching carril<->persona: subconjunto de tokens acotado por familia
(verificado 21/0 sobre datos reales). El codigo solo es ambiguo (AA dos
veces) y el nombre corto es substring fragil: solo la combinacion con la
familia del pase es robusta. Sin match unico no se inventa horario.
"""

from __future__ import annotations

import logging
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

from adapter import WINDOW_MINUTES
from column_map import get_pool_name

logger = logging.getLogger(__name__)

SHIFT_FILE_PATTERN = "horarios_importados_*.json"

# Sheet del JSON -> familias que cubre. PoolPases es el pool generico
# AgileOps (ORO + Prod); la desambiguacion fina la da la familia del pase.
SHEET_FAMILIES: dict[str, tuple[str, ...]] = {
    "PoolSF": ("S&F",),
    "PoolYape": ("Yape",),
    "PoolPases": ("AgileOps ORO", "AgileOps Prod"),
}


def normalize_person(value: Any) -> tuple[str, ...]:
    """Tokens minusculos sin acentos ni puntos para comparar nombres."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    ascii_text = text.encode("ascii", "ignore").decode("ascii")
    return tuple(t for t in ascii_text.lower().replace(".", " ").split() if t)


def find_shifts_file(
    input_dir: str | Path, pattern: str = SHIFT_FILE_PATTERN
) -> Path | None:
    """El match mas nuevo por mtime, o None si no hay archivo (degradado).

    Un patron sin comodines que apunta a un archivo existente se usa tal cual.
    """
    base = Path(input_dir)
    direct = base / pattern
    if direct.is_file():
        return direct
    if not base.is_dir():
        return None
    matches = [p for p in sorted(base.glob(pattern)) if p.is_file()]
    if not matches:
        return None
    return max(matches, key=lambda p: p.stat().st_mtime)


def _parse_shift(raw: dict[str, Any]) -> tuple[datetime, datetime]:
    return (
        datetime.fromisoformat(str(raw["start"])),
        datetime.fromisoformat(str(raw["end"])),
    )


def load_shifts(path: str | Path) -> dict[str, Any]:
    """Carga y normaliza el JSON de turnos. Falla fuerte si malformado."""
    import json

    target = Path(path)
    payload = json.loads(target.read_text(encoding="utf-8"))
    people: list[dict[str, Any]] = []
    pools = payload.get("pools") or {}
    for sheet, pool in pools.items():
        families = SHEET_FAMILIES.get(str(sheet), ())
        for person in pool.get("people") or []:
            people.append(
                {
                    "code": str(person.get("code", "")),
                    "person": str(person.get("person", "")),
                    "families": families,
                    "shifts": [
                        _parse_shift(s) for s in (person.get("shifts") or [])
                    ],
                }
            )
    logger.info("Loaded %d shift people from %s", len(people), target)
    return {"people": people, "source": str(target)}


def match_person(
    responsable: str, family: str, people: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Una sola persona cuyo nombre cabe en el responsable y cubre la familia.

    Devuelve None si hay cero o mas de un candidato: sin match unico no hay
    sombreado (el carril va normal y se cuenta en diagnostico).
    """
    wanted = normalize_person(responsable)
    if not wanted:
        return None
    candidates = [
        p
        for p in people
        if family in p.get("families", ())
        and all(t in normalize_person(responsable) for t in normalize_person(p.get("person", "")))
        and normalize_person(p.get("person", ""))
    ]
    if len(candidates) != 1:
        return None
    return candidates[0]


def clip_shifts_to_window(
    shifts: list[tuple[datetime, datetime]],
    window_start: datetime,
    window_end: datetime,
) -> list[tuple[int, int]]:
    """Segmentos en turno recortados a la grilla [0, 480), ordenados."""
    base = window_start
    clipped: list[tuple[int, int]] = []
    for start, end in shifts:
        s = int(round((start - base).total_seconds() / 60))
        e = int(round((end - base).total_seconds() / 60))
        s, e = max(0, s), min(WINDOW_MINUTES, e)
        if e > s:
            clipped.append((s, e))
    return sorted(clipped)


def off_shift_segments(
    in_shift: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    """Complemento en [0, 480): lo que NO cubre ningun turno."""
    cursor = 0
    fuera: list[tuple[int, int]] = []
    for start, end in sorted(in_shift):
        if start > cursor:
            fuera.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < WINDOW_MINUTES:
        fuera.append((cursor, WINDOW_MINUTES))
    return fuera


def is_out_of_shift(
    inicio: Any,
    fin: Any,
    shifts: list[tuple[datetime, datetime]],
) -> bool:
    """True si el intervalo no solapa NINGUN turno (anomalia accionable).

    Sin fechas validas no se juzga: False, igual que colgados.
    """
    if not isinstance(inicio, datetime) or not isinstance(fin, datetime):
        return False
    if inicio != inicio or fin != fin:  # pandas NaT
        return False
    for start, end in shifts:
        if inicio < end and start < fin:
            return False
    return True


def _lane_key(responsable: Any) -> str:
    """La misma clave que usa el frontend para el carril (o Sin asignar)."""
    text = str(responsable or "").strip()
    if not text or text.lower() == "nan":
        return "Sin asignar"
    return text


def build_lane_shifts(
    rows: list[dict[str, Any]],
    people: list[dict[str, Any]],
    window_start: datetime,
    window_end: datetime,
) -> dict[str, dict[str, dict[str, Any]]]:
    """Payload por carril: {pool: {responsable: {matched, fuera}}}.

    `fuera` son segmentos [min, min] fuera de turno recortados a la grilla.
    Sin match unico: matched False y sin segmentos (carril normal).
    """
    lanes: dict[str, dict[str, dict[str, Any]]] = {}
    seen: set[tuple[str, str]] = set()
    for row in rows:
        pool = get_pool_name(row.get("recurso", ""))
        resp = _lane_key(row.get("responsable", ""))
        if (pool, resp) in seen:
            continue
        seen.add((pool, resp))
        person = match_person(resp, pool, people)
        if person is None:
            lanes.setdefault(pool, {})[resp] = {"matched": False, "fuera": []}
            continue
        segs = clip_shifts_to_window(person["shifts"], window_start, window_end)
        fuera = [list(seg) for seg in off_shift_segments(segs)]
        lanes.setdefault(pool, {})[resp] = {"matched": True, "fuera": fuera}
    return lanes


def collect_out_of_shift(
    rows: list[dict[str, Any]],
    people: list[dict[str, Any]],
) -> list[str]:
    """Tickets cuyo intervalo no solapa ningun turno de su persona.

    Solo personas matcheadas con fechas validas: lo demas no se juzga.
    """
    tickets: list[str] = []
    for row in rows:
        pool = get_pool_name(row.get("recurso", ""))
        person = match_person(
            _lane_key(row.get("responsable", "")), pool, people
        )
        if person is None:
            continue
        if is_out_of_shift(
            row.get("inicio_impl"), row.get("fin_impl"), person["shifts"]
        ):
            ticket = str(row.get("ticket", "") or "").strip()
            if ticket:
                tickets.append(ticket)
    return tickets
