"""
Adapter: converts normalized Excel rows to Data Contract v1.

ADR-004: All times are converted to minutes from window start.
         The frontend never parses "HH:MM" strings for positioning.

ADR-012 (supersedes ADR-005's anchor): The 8-hour window is anchored
         dynamically to the RUN CLOCK (the system time at run, or an explicit
         --now override), floored to the hour. The window size stays fixed at
         8h; only its start moves. The Excel mtime is diagnostic only.
         See docs/ARCHITECTURE_DECISIONS.md (ADR-012).

Pool scope: the whitelist and the pool family table live in column_map.py.
             This module imports them — it never re-declares a pool value.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from column_map import (
    IN_SCOPE_POOL_KEYS,
    POOL_FAMILY_ORDER,
    get_pool_name,
    normalize_recurso,
    visibility_groups,
)

logger = logging.getLogger(__name__)

# Resource/state normalization (upper-case, remove ALL whitespace) lives in
# column_map together with the pool whitelist, so the two can never drift.
# _norm_key is the historical private name used by the call sites below.
_norm_key = normalize_recurso

# Window configuration (ADR-012)
WINDOW_HOURS = 8
WINDOW_MINUTES = 480  # 8 hours

# Fallback anchor when no update timestamp is available
_HOUR = timedelta(hours=1)


def floor_to_hour(dt: datetime) -> datetime:
    """Floor a datetime to the start of its hour."""
    return dt.replace(minute=0, second=0, microsecond=0)


def compute_window(reference_dt: datetime) -> dict[str, Any]:
    """
    Compute the dynamic 8h window anchored to the SINGLE temporal reference
    (ADR-012, which supersedes ADR-005's Excel-mtime anchor).

    The anchor is `reference_dt` — the RUN CLOCK captured once in
    `main.main()` (or the explicit `--now` override) — floored to the hour.
    Window end = anchor + 8h. The Excel mtime is never passed here; it is
    diagnostic information only.

    Returns a dict:
        {
          "start": datetime,      # window start (floored to hour)
          "end": datetime,        # window end (start + 8h)
          "start_hhmm": "HH:MM",
          "end_hhmm": "HH:MM",
          "updated_at": datetime, # the reference stamp (run clock)
        }
    """
    start = floor_to_hour(reference_dt)
    end = start + timedelta(hours=WINDOW_HOURS)

    window = {
        "start": start,
        "end": end,
        "start_hhmm": start.strftime("%H:%M"),
        "end_hhmm": end.strftime("%H:%M"),
        "updated_at": reference_dt,
    }

    logger.info(
        "ADR-012 window anchored to %s → [%s, %s]",
        reference_dt.isoformat(sep=" "),
        window["start_hhmm"],
        window["end_hhmm"],
    )

    return window


def filter_to_window(
    rows: list[dict[str, Any]],
    window: dict[str, Any],
) -> tuple[list[dict[str, Any]], int]:
    """
    Keep rows that overlap the window (ADR-012 window, T14 overlap scope).

    A row is kept when its implementation START falls inside the window
    (status quo) OR when it started before the window but proves overlap
    with a valid FIN past the window start (T14: lanes read occupied NOW).
    Without a valid FIN there is no provable overlap, so the row drops out.

    Returns:
        (kept_rows, dropped_count)
    """
    start = window["start"]
    end = window["end"]

    kept: list[dict[str, Any]] = []
    dropped = 0

    for row in rows:
        inicio = row.get("inicio_impl")
        if not isinstance(inicio, datetime):
            dropped += 1
            continue
        if start <= inicio < end:
            kept.append(row)
            continue
        fin = row.get("fin_impl")
        if inicio < start and _is_valid_dt(fin) and fin > start:
            kept.append(row)
        else:
            dropped += 1

    logger.info(
        "Window filter: %d kept, %d outside window", len(kept), dropped
    )
    return kept, dropped


def hhmm_to_minutes(hhmm: str, window_start_hhmm: str) -> int:
    """
    Convert "HH:MM" to minutes from window start (ADR-004).

    Args:
        hhmm: Time string like "00:30" or "23:45"
        window_start_hhmm: Window start like "23:00"

    Returns:
        Minutes from window start (can be negative if before window).

    Examples:
        >>> hhmm_to_minutes("23:00", "23:00")
        0
        >>> hhmm_to_minutes("23:30", "23:00")
        30
        >>> hhmm_to_minutes("00:00", "23:00")
        60
        >>> hhmm_to_minutes("01:30", "23:00")
        150
    """
    parts = hhmm.split(":")
    h, m = int(parts[0]), int(parts[1])
    total_min = h * 60 + m

    start_parts = window_start_hhmm.split(":")
    start_h, start_m = int(start_parts[0]), int(start_parts[1])
    start_total = start_h * 60 + start_m

    diff = total_min - start_total
    # Handle midnight crossing
    if diff < -720:
        diff += 1440
    elif diff > 720:
        diff -= 1440

    return diff


def minutes_to_hhmm(minutes: int, window_start_hhmm: str) -> str:
    """
    Convert minutes from window start back to "HH:MM" (ADR-004).
    """
    start_parts = window_start_hhmm.split(":")
    start_h, start_m = int(start_parts[0]), int(start_parts[1])
    start_total = start_h * 60 + start_m

    total = (start_total + minutes) % 1440
    h = total // 60
    m = total % 60
    return f"{h:02d}:{m:02d}"


def datetime_to_window_minutes(dt: datetime, window_start_dt: datetime) -> int:
    """
    Real minutes from the window start datetime (ADR-004, v1.1.6).

    Day-aware: rows on other dates yield the correct offset, which lets the
    frontend render the full date (DD/MM HH:MM) in the operational table.
    """
    return int(round((dt - window_start_dt).total_seconds() / 60))


def get_bar_type(row: dict[str, Any]) -> str:
    """
    Determine if a row is 'implementacion' or 'derivado'.

    Logic: if the resource contains DERIVADO, it's a derivative.
    """
    recurso = str(row.get("recurso", "")).upper()
    if "DERIVADO" in recurso:
        return "derivado"
    return "implementacion"


def get_bar_status(row: dict[str, Any], late_start: bool = False) -> str:
    """
    Determine the visual status of a bar.

    Returns: "coordinado", "pase-en-curso", or "inicio-atrasado"
    """
    if late_start:
        return "inicio-atrasado"

    estado = str(row.get("estado", "")).strip().lower()
    if "pase en curso" in estado:
        return "pase-en-curso"

    return "coordinado"


# ---------------------------------------------------------------
# Timeline operational states (v1.1.6)
# ---------------------------------------------------------------

# The Timeline only shows ACTIVE operational states. Anything else
# (Terminado Satisfactorio, Cerrado, Rechazado, Pre Registrado, Registrado,
# Aprobado LT/CL QA/CL DEV/PO/Ops, Ratificación Total Satisfactorio, …) is
# excluded, even if it falls inside the window.
TIMELINE_ALLOWED_STATES = {"coordinado", "pase en curso"}


def is_timeline_state(estado: Any) -> bool:
    """True only for the active operational states shown in the Timeline."""
    return str(estado or "").strip().lower() in TIMELINE_ALLOWED_STATES


# ---------------------------------------------------------------
# Operational table scope (v1.1.1)
# ---------------------------------------------------------------

# Resources included in the operational table. Sourced from column_map, which
# owns the pool list; this alias exists so the existing call sites in this
# module keep working without a second literal copy.
OPERATIONAL_RESOURCES = frozenset(IN_SCOPE_POOL_KEYS)

# States EXCLUDED from the operational table (normalized, whitespace removed).
# NOTE: the spec lists "Rechazado por Gestor de cambio"; the workbook's actual
# value is "Rechazado", so both normalized forms are excluded.
EXCLUDED_TABLE_STATES = {
    _norm_key("Rechazado por Gestor de cambio"),
    _norm_key("Rechazado"),
    _norm_key("Pre Registrado"),
    _norm_key("Registrado"),
    _norm_key("Aprobado LT"),
    _norm_key("Aprobado CL QA"),
    _norm_key("Aprobado CL DEV"),
    _norm_key("Aprobado PO"),
}


def is_operational_resource(recurso: Any) -> bool:
    """True if the resource belongs to the operational table whitelist."""
    return _norm_key(recurso) in OPERATIONAL_RESOURCES


def is_table_state_allowed(estado: Any) -> bool:
    """True if the state is NOT excluded from the operational table."""
    return _norm_key(estado) not in EXCLUDED_TABLE_STATES


def build_operational_table(
    rows: list[dict[str, Any]],
    window_start: str,
    reference_dt: datetime | None = None,
) -> list[dict[str, Any]]:
    """
    Build the operational table from the FULL in-scope pool universe.

    - Exact resource whitelist (column_map, normalized for spacing/case).
    - Excludes the configured states.
    - Keeps only LIVE work — rows whose FEC. HORA. FIN. IMPL is not
      before `reference_dt` (the run reference). Finished implementations drop out.
    - The entry name is NOMBRE APP.
    - One row per record (no dedup). Sorted by planned start (ascending).
    """
    selected: list[tuple[datetime, dict[str, Any]]] = []

    for row in rows:
        if not is_operational_resource(row.get("recurso", "")):
            continue
        # v1.1.7: the table shows ONLY active operational states
        # (Coordinado / Pase en curso), same set as the Timeline.
        if not is_timeline_state(row.get("estado", "")):
            continue
        if reference_dt is not None:
            fin = row.get("fin_impl")
            if _is_valid_dt(fin) and fin < reference_dt:
                continue
        entry = _row_to_table_entry(row)
        inicio = row.get("inicio_impl")
        if entry is not None and _is_valid_dt(inicio):
            selected.append((inicio, entry))

    selected.sort(key=lambda pair: pair[0])
    return [entry for _, entry in selected]


def _ordered_pool_groups(pools: dict[str, list[dict]]) -> list[str]:
    """
    Pool group keys in the canonical display order.

    In-scope families come first, in the order declared by column_map (which is
    the same order published as meta.poolOrder). Any unexpected key is kept
    afterwards in alphabetical order so an unmapped resource can never be
    silently dropped from the timeline.
    """
    families = [name for name in POOL_FAMILY_ORDER if name in pools]
    leftovers = sorted(name for name in pools if name not in POOL_FAMILY_ORDER)
    return families + leftovers


def to_contract(
    rows: list[dict[str, Any]],
    diagnostic: dict[str, Any] | None = None,
    window: dict[str, Any] | None = None,
    table_rows: list[dict[str, Any]] | None = None,
    table_reference_dt: datetime | None = None,
) -> dict[str, Any]:
    """
    Convert normalized Excel rows to Data Contract v1.

    Args:
        rows: In-window normalized rows (already filtered by the window)
        diagnostic: Optional diagnostic data (unused here, kept for API)
        window: Window dict from compute_window(). REQUIRED — see below.

    Returns:
        dict conforming to DATA_CONTRACT.md

    Raises:
        ValueError: when `window` is None. There is intentionally NO fallback:
            an internal `compute_window(datetime.now())` used to read the wall
            clock while the caller used the Excel mtime, i.e. two temporal
            references in one contract. Every caller now passes the window
            computed once from the single run reference (ADR-012), so a missing
            window is a programming error and must fail loudly.
    """
    if window is None:
        raise ValueError(
            "to_contract() requires a `window` computed from the single run "
            "reference (ADR-012): pass compute_window(reference_dt). The old "
            "datetime.now() fallback was a second temporal reference and was "
            "removed on purpose."
        )
    wstart = window["start"]   # datetime — day-aware minutes

    # Timeline groups keep the display pool FAMILY resolved from the real
    # RECURSO value. The render-only grouping by RECURSO ASIGNADO happens in
    # the frontend, derived from the window.ChangeOpsActions payload (which
    # carries `resource` per ticket).
    pools: dict[str, list[dict]] = {}
    for row in rows:
        # The Timeline only shows ACTIVE operational states.
        if not is_timeline_state(row.get("estado", "")):
            continue
        pool = get_pool_name(row.get("recurso", ""))
        pools.setdefault(pool, []).append(row)

    timeline = []
    for pool_name in _ordered_pool_groups(pools):
        bars = []
        for row in pools[pool_name]:
            bar = _row_to_bar(row, wstart)
            if bar:
                bars.append(bar)
        if bars:
            timeline.append({"pool": pool_name, "bars": bars})

    # Build the table from the full operational universe when provided,
    # otherwise fall back to the timeline rows.
    if table_rows is not None:
        table = build_operational_table(
            table_rows, wstart, reference_dt=table_reference_dt
        )
    else:
        table = []
        for row in rows:
            entry = _row_to_table_entry(row)
            if entry:
                table.append(entry)

    contract = {
        "meta": {
            "updatedAt": window["updated_at"].strftime("%Y-%m-%dT%H:%M:%S"),
            "windowStart": window["start_hhmm"],
            "windowEnd": window["end_hhmm"],
            # Display order of the pool families, emitted from Python so the
            # web layer stops hardcoding it. Always the full list, even when a
            # family has zero bars in the window.
            "poolOrder": list(POOL_FAMILY_ORDER),
            # The 3 pool visibility groups, published the same way poolOrder
            # is (ADR-011): the web layer never hardcodes the group list, and
            # each entry is derived from the family table in column_map.
            # Per-group KPIs and action ticket sets are filled in afterwards
            # by kpi.update_contract_visibility_kpis().
            "visibilityGroups": visibility_groups(),
        },
        "kpis": {
            "lateStarts": 0,  # Calculated by kpi.py
            "ratificationsSoon": 0,
            "ratificationsExpired": 0,
            "reversions": 0,
        },
        "timeline": timeline,
        "table": table,
    }

    return contract


def _is_valid_dt(value: Any) -> bool:
    """True for a real datetime (rejects None, float NaN and pandas NaT)."""
    return isinstance(value, datetime) and value == value


def _compute_start_duration(
    row: dict[str, Any], window_start: str, enforce_window: bool = True
) -> tuple[int, int] | None:
    """
    Compute (start_min, duration_min) relative to the window.

    enforce_window=True (timeline): requires start inside [0, 480) and clips
    the end to the grid.
    enforce_window=False (operational table, v1.1.1): keeps any start
    (can be negative for out-of-window rows); duration is the real one.

    Returns None if the row is invalid or the duration is non-positive.
    T14: a row started before the window but still alive at its left edge is
    drawn clipped (start 0, visible duration) so lane occupancy reads NOW.
    """
    inicio_impl = row.get("inicio_impl")
    fin_impl = row.get("fin_impl")

    if not _is_valid_dt(inicio_impl) or not _is_valid_dt(fin_impl):
        return None

    start_min = datetime_to_window_minutes(inicio_impl, window_start)
    # Duration from the real delta (robust across midnight / multi-day).
    duration = int(round((fin_impl - inicio_impl).total_seconds() / 60))

    if duration <= 0:
        return None

    if enforce_window:
        if start_min >= WINDOW_MINUTES:
            return None
        # Clip both edges to the grid: a pre-window start lands on 0 and an
        # overflowing end lands on 480. A row with nothing visible drops out.
        visible_start = max(0, start_min)
        visible_end = min(start_min + duration, WINDOW_MINUTES)
        if visible_end <= visible_start:
            return None
        return visible_start, visible_end - visible_start

    return start_min, duration


def _row_to_bar(row: dict[str, Any], window_start: str) -> dict[str, Any] | None:
    """Convert a single row to a timeline bar (ADR-004 minutes, ADR-012 window)."""
    ticket = row.get("ticket", "")
    if not ticket:
        return None

    computed = _compute_start_duration(row, window_start)
    if computed is None:
        return None
    start_min, duration = computed

    bar_type = get_bar_type(row)
    late_start = row.get("_late_start", False)
    status = get_bar_status(row, late_start)

    return {
        "ticket": str(ticket),
        # v1.1.4: the bar name carries NOMBRE APP (the bar label itself shows
        # only the ticket, rendered by the frontend).
        "name": str(row.get("nombre_app", "") or ticket).strip()[:50],
        "type": bar_type,
        "start": start_min,
        "duration": duration,
        "status": status,
    }


def _row_to_table_entry(row: dict[str, Any]) -> dict[str, Any] | None:
    """
    Convert a single row to an operational table entry.

    Shape (column order):
        responsable, pool, type, ticket, nombre_app, status,
        inicio_impl, fin_impl   (dates as "DD/MM HH:MM").
    """
    ticket = row.get("ticket", "")
    if not ticket:
        return None

    inicio = row.get("inicio_impl")
    fin = row.get("fin_impl")
    if not _is_valid_dt(inicio) or not _is_valid_dt(fin):
        return None

    bar_type = get_bar_type(row)

    return {
        "responsable": str(row.get("responsable", "") or "").strip(),
        "pool": get_pool_name(row.get("recurso", "")),
        "type": "Implementación" if bar_type == "implementacion" else "Derivado",
        "ticket": str(ticket),
        "nombre_app": str(row.get("nombre_app", "") or "").strip(),
        "status": str(row.get("estado", "")).strip(),
        "inicio_impl": inicio.strftime("%d/%m %H:%M"),
        "fin_impl": fin.strftime("%d/%m %H:%M"),
    }
