"""Shifts loader: turnos por recurso para sombrear carriles fuera de turno.

Dos esquemas de entrada (load_shifts detecta por contenido):

- Legacy (octubre 2026, armado a mano): ``{"pools": {hoja: {people: [...]}}}``.
  Estructura: pools (sheets) -> people (code, person, shifts con start/end
  ISO). Los calendarios traen datetimes absolutas, asi el cruce de medianoche
  sale solo.
- Flat (export del cliente, noviembre 2026 en adelante): ``{"people": [...]}``
  con ``hoja``, ``pool``, ``fecha``, ``tipoHorario`` y shifts absolutos. Los
  registros de la misma persona en varias hojas se fusionan en un unico
  candidato: su disponibilidad es la UNION de todas sus pistas (``Normal`` y
  ``Derivado``). La hoja PoolPases-D no aporta horas fuera de la hoja
  normal (verificado sobre todo noviembre) y el tipo de barra del pase se
  ignora al sombrear: fuera de turno = no disponible en ninguna pista.
  PoolCapacity (cubre vacaciones/licencias/ausencias) matchea en cualquier
  familia de pool.

Las hojas que no hacen pases se descartan por config ``shifts.excluded_sheets``
(default: PoolProyecto, LEGACY, SAMAY1, Samay2). Hojas nuevas sin mapeo se
ignoran con warning: nunca se inventa horario.

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
from typing import Any, Iterable

from adapter import WINDOW_MINUTES
from column_map import POOL_FAMILY_ORDER, get_pool_name

logger = logging.getLogger(__name__)

SHIFT_FILE_PATTERN = "horarios_importados_*.json"

NORMAL_TRACK = "normal"
DERIVADO_TRACK = "derivado"

# Sheet del JSON legacy -> familias que cubre. PoolPases es el pool generico
# AgileOps (ORO + Prod); la desambiguacion fina la da la familia del pase.
SHEET_FAMILIES: dict[str, tuple[str, ...]] = {
    "PoolSF": ("S&F",),
    "PoolYape": ("Yape",),
    "PoolPases": ("AgileOps ORO", "AgileOps Prod"),
}

# Hoja del export flat del cliente -> familias que cubre. El export mismo
# marca la pista de cada registro con tipoHorario: "Normal" | "Derivado".
# PoolPases-D es la MISMA gente con horario derivado, no otra familia.
HOJA_FAMILIES: dict[str, tuple[str, ...]] = {
    "PoolSF": ("S&F",),
    "YAPE": ("Yape",),
    "PoolPases": ("AgileOps ORO", "AgileOps Prod"),
    "PoolPases-D": ("AgileOps ORO", "AgileOps Prod"),
    # Capacity cubre vacaciones, descansos medicos, licencias y ausencias de
    # cualquier pool: matchea en todas las familias operativas.
    "PoolCapacity": ("Yape", "S&F", "AgileOps ORO", "AgileOps Prod"),
}

# Hojas sin contenido operativo para la app del cliente; no hacen pases y no
# deben figurar en el timeline. Configurable en config.yaml.
DEFAULT_EXCLUDED_SHEETS: tuple[str, ...] = (
    "PoolProyecto",
    "LEGACY",
    "SAMAY1",
    "Samay2",
)

_TRACK_KEY = {
    "Derivado": DERIVADO_TRACK,
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


def _track_for(tipo_horario: Any) -> str:
    """Hoja tipoHorario -> pista de horario ("normal" salvo "Derivado")."""
    return _TRACK_KEY.get(str(tipo_horario or "").strip(), NORMAL_TRACK)


def _families_in_order(fams: Iterable[str]) -> tuple[str, ...]:
    """Familias en el orden canonico de display (poolOrder)."""
    idx = {f: i for i, f in enumerate(POOL_FAMILY_ORDER)}
    unknown = [f for f in fams if f not in idx]
    if unknown:
        logger.warning("Familias sin orden canonico: %s", unknown)
    return tuple(sorted(set(fams), key=lambda f: idx.get(f, len(idx))))


def _load_legacy(pools: Any) -> tuple[list, dict[str, int]]:
    """Schema legacy: hojas -> people {code, person, shifts}."""
    people: list[dict[str, Any]] = []
    for sheet, pool in (pools or {}).items():
        families = SHEET_FAMILIES.get(str(sheet), ())
        for person in pool.get("people") or []:
            shifts = [_parse_shift(s) for s in (person.get("shifts") or [])]
            people.append(
                {
                    "code": str(person.get("code", "")),
                    "person": str(person.get("person", "")),
                    "families": families,
                    "shifts": shifts,
                    "tracks": {NORMAL_TRACK: shifts},
                }
            )
    return people, {}


def _load_flat(
    records: Any, excluded: tuple[str, ...]
) -> tuple[list, dict[str, int]]:
    """Schema flat del cliente: registros por persona/hoja -> un candidato."""
    excluded_folded = {str(e or "").strip().casefold() for e in excluded}
    groups: dict[str, dict[str, Any]] = {}
    skipped: dict[str, int] = {}
    for rec in records or []:
        hoja = str(rec.get("hoja", "") or "").strip()
        folded = hoja.casefold()
        if not hoja or folded in excluded_folded:
            if hoja:
                skipped[hoja] = skipped.get(hoja, 0) + 1
            continue
        families = HOJA_FAMILIES.get(hoja)
        if families is None:
            logger.warning("Hoja de horarios sin mapeo: %r; se ignora", hoja)
            skipped[hoja] = skipped.get(hoja, 0) + 1
            continue
        name = str(rec.get("person", "") or "")
        group = groups.setdefault(
            name, {"person": name, "families": set(), "tracks": {}}
        )
        group["families"].update(families)
        track = _track_for(rec.get("tipoHorario"))
        group["tracks"].setdefault(track, [])
        group["tracks"][track].extend(
            _parse_shift(s) for s in (rec.get("shifts") or [])
        )
    people: list[dict[str, Any]] = []
    for group in groups.values():
        tracks: dict[str, list[tuple[datetime, datetime]]] = {}
        for track, shifts in group["tracks"].items():
            tracks[track] = sorted(shifts)
        people.append(
            {
                "code": "",
                "person": group["person"],
                "families": _families_in_order(group["families"]),
                "tracks": tracks,
                "shifts": tracks.get(NORMAL_TRACK, []),
            }
        )
    people.sort(key=lambda p: p["person"].casefold())
    return people, skipped


def load_shifts(
    path: str | Path, excluded_sheets: Iterable[str] | None = None
) -> dict[str, Any]:
    """Carga y normaliza el JSON de turnos. Falla fuerte si malformado.

    Deteccion por contenido: ``pools`` -> legacy; ``people`` -> flat del
    cliente. ``excluded_sheets`` solo aplica al esquema flat (default:
    DEFAULT_EXCLUDED_SHEETS).
    """
    import json

    target = Path(path)
    payload = json.loads(target.read_text(encoding="utf-8"))
    excluded = (
        tuple(DEFAULT_EXCLUDED_SHEETS)
        if excluded_sheets is None
        else tuple(excluded_sheets)
    )
    if "pools" in payload:
        people, skipped = _load_legacy(payload.get("pools") or {})
        schema = "legacy"
    elif isinstance(payload.get("people"), list):
        people, skipped = _load_flat(payload["people"], excluded)
        schema = "flat"
    else:
        raise ValueError(f"Esquema de shifts no reconocido: {target}")
    if skipped:
        logger.info(
            "Hojas de horarios sin uso (excluidas/sin mapeo): %s", skipped
        )
    logger.info(
        "Loaded %d shift people from %s (schema=%s)", len(people), target, schema
    )
    return {
        "people": people,
        "source": str(target),
        "schema": schema,
        "skipped_sheets": skipped,
    }


def match_person(
    responsable: str,
    family: str,
    people: list[dict[str, Any]],
    track: str = NORMAL_TRACK,
) -> dict[str, Any] | None:
    """Una sola persona cuyo nombre cabe en el responsable y cubre la familia.

    Devuelve None si hay cero o mas de un candidato: sin match unico no hay
    sombreado (el carril va normal y se cuenta en diagnostico). ``track``
    queda por compatibilidad pero YA NO selecciona: los shifts devueltos son
    la union de todas las pistas de la persona, porque fuera de turno debe
    significar "no disponible en ninguna pista" aunque un carril mezcle
    pases normales y derivados.
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
    person = candidates[0]
    return {
        "person": person["person"],
        "families": person.get("families", ()),
        "shifts": _person_availability(person),
    }


def _person_availability(
    person: dict[str, Any]
) -> list[tuple[datetime, datetime]]:
    """Union de todas las pistas, intervalos solapados/fusionados.

    Acepta el dict del loader (``tracks``) y el dict plano de tests legacy
    (solo ``shifts``). La hoja -(D)erivado es subconjunto de la normal para
    todas las personas del export real, pero si un dia derivado apareciera
    fuera de la normal, la union lo mantiene: es disponibilidad real.
    """
    tracks = person.get("tracks") or person.get("shifts_by_track") or {}
    raw: list[tuple[datetime, datetime]] = list(person.get("shifts") or [])
    for shifts in tracks.values():
        raw.extend(shifts)
    merged: list[tuple[datetime, datetime]] = []
    for start, end in sorted(raw):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


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
    Sin match unico: matched False y sin segmentos (carril normal). El tipo
    de barra no cambia el sombreado: la disponibilidad de la persona es la
    union de todas sus pistas.
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
