"""
Business rules: late starts, ratifications, conflicts.

Rules operate on the in-scope pool rows (see column_map) and annotate flags
consumed by the adapter (status) and kpi.py (counts).

ADR-012 (supersedes ADR-005's anchor): the temporal reference is
         meta.updatedAt, which is now the RUN CLOCK captured once per run (or
         the explicit --now override). The Excel mtime is diagnostic only and
         never reaches these rules.
ADR-006: TERMINAL states (Cerrado, Terminado Satisfactorio, Rechazado,
         Cancelado, Anulado, Registrado, the approval family Aprobado *
         and equivalents) are EXCLUDED from the operational KPIs and from
         conflict detection. They never produce late starts, ratification
         alerts, or conflicts.
"""

from __future__ import annotations

import logging
import unicodedata
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# Time thresholds (in minutes)
LATE_START_THRESHOLD = 5          # > 5 min past planned start while still Coordinado
RATIFICATION_SOON_THRESHOLD = 10  # ≤ 10 min before ratification END = about to expire

# ADR-006 (enmienda 2026-10-21): terminal-state keywords (normalized:
# lowercase, no accents)
# NOTE: "registrado" also matches "Pre Registrado" by substring — intended,
# both are pre-execution states excluded from operational KPIs.
# NOTE: "aprobado" covers the whole approval family (Aprobado LT/CL QA/
# CL DEV/PO/Ops) and "Preaprobado" — approval states are inactive work and
# must not raise ratification alerts or conflicts (user report: "Aprobado LT"
# leaking into the Ratificaciones vencidas KPI, tickets OCD-237620,
# MVPLEGBCP-252621).
TERMINAL_STATE_KEYWORDS = (
    "cerrado",
    "terminado",
    "rechazado",
    "cancelado",
    "anulado",
    "registrado",
    "aprobado",
)


def normalize_state(estado: Any) -> str:
    """Lowercase, strip and remove accents for robust state matching."""
    text = str(estado or "")
    decomposed = unicodedata.normalize("NFKD", text)
    ascii_text = decomposed.encode("ascii", "ignore").decode("ascii")
    return ascii_text.lower().strip()


def is_terminal(estado: Any) -> bool:
    """True if the state is terminal (ADR-006)."""
    norm = normalize_state(estado)
    return any(keyword in norm for keyword in TERMINAL_STATE_KEYWORDS)


def filter_operational(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return only non-terminal rows — the operational KPI scope (ADR-006)."""
    return [r for r in rows if not is_terminal(r.get("estado", ""))]


def apply_rules(
    rows: list[dict[str, Any]],
    reference_now: datetime,
) -> list[dict[str, Any]]:
    """
    Apply all business rules to the in-scope pool rows.

    Modifies rows in-place, adding rule flags:
        - _late_start: bool
        - _ratification_soon: bool
        - _ratification_expired: bool
        - _conflicts_with: list of ticket IDs

    Terminal rows (ADR-006) keep all flags False and never join conflicts.

    Args:
        rows: In-scope normalized rows (see column_map)
        reference_now: Temporal reference (meta.updatedAt)

    Returns the same rows for chaining.
    """
    rows = _apply_late_start(rows, reference_now)
    rows = _apply_ratification_rules(rows, reference_now)
    rows = _detect_conflicts(rows)
    return rows


def _apply_late_start(
    rows: list[dict[str, Any]],
    reference_now: datetime,
) -> list[dict[str, Any]]:
    """
    Rule: Inicio atrasado.

    Condition: Estado == "Coordinado" AND the reference time is more than
    LATE_START_THRESHOLD minutes past the planned implementation start.
    Terminal rows never qualify (ADR-006).
    """
    for row in rows:
        row["_late_start"] = False

        if is_terminal(row.get("estado", "")):
            continue

        if normalize_state(row.get("estado", "")) != "coordinado":
            continue

        inicio_impl = row.get("inicio_impl")
        if not isinstance(inicio_impl, datetime):
            continue

        minutes_past = (reference_now - inicio_impl).total_seconds() / 60
        if minutes_past > LATE_START_THRESHOLD:
            row["_late_start"] = True
            logger.debug(
                "Late start: %s (%.0f min past planned start, still Coordinado)",
                row.get("ticket"),
                minutes_past,
            )

    return rows


def _apply_ratification_rules(
    rows: list[dict[str, Any]],
    reference_now: datetime,
) -> list[dict[str, Any]]:
    """
    Rules:
    - Ratificación por vencer: reference_now within RATIFICATION_SOON_THRESHOLD
      minutes BEFORE the ratification END (FIN_RATI) — the window is about to
      close. Enmienda 2026-10-21 (ADR-007): the old rule anchored on the START
      (inicio_rati), which flagged windows about to OPEN; "por vencer" must
      pair with "vencida" (now > FIN_RATI) on the same FIN_RATI axis.
    - Ratificación vencida: reference_now past the ratification end.

    Terminal rows are skipped entirely (ADR-006).
    """
    for row in rows:
        row["_ratification_soon"] = False
        row["_ratification_expired"] = False

        if is_terminal(row.get("estado", "")):
            continue

        inicio_rati = row.get("inicio_rati")
        fin_rati = row.get("fin_rati")

        if not isinstance(inicio_rati, datetime) or not isinstance(fin_rati, datetime):
            continue

        minutes_to_end = (fin_rati - reference_now).total_seconds() / 60
        if 0 <= minutes_to_end <= RATIFICATION_SOON_THRESHOLD:
            row["_ratification_soon"] = True
            logger.debug(
                "Ratification soon: %s (%.0f min to ratification end)",
                row.get("ticket"),
                minutes_to_end,
            )

        if reference_now > fin_rati:
            row["_ratification_expired"] = True
            logger.debug("Ratification expired: %s", row.get("ticket"))

    return rows


def _detect_conflicts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Rule: Conflicto.

    Conditions (all required):
    - Same responsible person (RECURSO ASIGNADO)
    - Both are Implementation (never Derivado)
    - Time overlap of the implementation intervals
    - Neither row is terminal (ADR-006)
    """
    for row in rows:
        row["_conflicts_with"] = []

    by_responsible: dict[str, list[dict]] = {}
    for row in rows:
        if is_terminal(row.get("estado", "")):
            continue
        if not _is_implementation(row):
            continue
        responsable = str(row.get("responsable", "")).strip()
        if not responsable or responsable.lower() == "nan":
            continue
        by_responsible.setdefault(responsable, []).append(row)

    for responsable, group in by_responsible.items():
        for i, row_a in enumerate(group):
            for j, row_b in enumerate(group):
                if i >= j:
                    continue
                if _has_time_overlap(row_a, row_b):
                    row_a["_conflicts_with"].append(row_b.get("ticket", ""))
                    row_b["_conflicts_with"].append(row_a.get("ticket", ""))
                    logger.debug(
                        "Conflict: %s vs %s (responsable=%s)",
                        row_a.get("ticket"),
                        row_b.get("ticket"),
                        responsable,
                    )

    return rows


def _is_implementation(row: dict[str, Any]) -> bool:
    """A row is implementation unless its resource marks it as DERIVADO."""
    return "DERIVADO" not in str(row.get("recurso", "")).upper()


def _has_time_overlap(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Check if two rows have overlapping implementation intervals."""
    a_start = a.get("inicio_impl")
    a_end = a.get("fin_impl")
    b_start = b.get("inicio_impl")
    b_end = b.get("fin_impl")

    if not all(isinstance(d, datetime) for d in [a_start, a_end, b_start, b_end]):
        return False

    return a_start < b_end and b_start < a_end


def collect_conflicts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return unique conflict pairs as structured dicts (diagnostic report)."""
    pairs: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for row in rows:
        ticket_a = str(row.get("ticket", ""))
        for other in row.get("_conflicts_with", []):
            key = tuple(sorted([ticket_a, str(other)]))
            if key in seen:
                continue
            seen.add(key)
            pairs.append(
                {
                    "tickets": [key[0], key[1]],
                    "responsable": str(row.get("responsable", "")).strip(),
                }
            )

    return pairs


def count_late_starts(rows: list[dict[str, Any]]) -> int:
    return sum(1 for r in rows if r.get("_late_start", False))


def count_ratifications_soon(rows: list[dict[str, Any]]) -> int:
    return sum(1 for r in rows if r.get("_ratification_soon", False))


def count_ratifications_expired(rows: list[dict[str, Any]]) -> int:
    return sum(1 for r in rows if r.get("_ratification_expired", False))


def count_conflicts(rows: list[dict[str, Any]]) -> int:
    """Count rows involved in at least one conflict."""
    return sum(1 for r in rows if r.get("_conflicts_with", []))
