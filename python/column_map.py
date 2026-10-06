"""
Column mapping: Excel columns → internal field names.

The Excel file uses Spanish column names with inconsistent spacing
and punctuation. This module maps them to clean internal names.

Operational scope: the 4 AgileOps Prod pool families (Yape, S&F,
AgileOps ORO, AgileOps Prod). The pool list lives HERE and only here —
adapter.py imports it, so there is a single source of truth.
"""

from __future__ import annotations

from typing import Any

# Excel column name → internal field name
COLUMN_MAP: dict[str, str] = {
    # Identity
    "TRIBU": "tribu",
    "SQUAD": "squad",
    "TICKET": "ticket",
    "NOMBRE APP": "nombre_app",
    "DESCRIPCIÓN DEL CAMBIO": "descripcion",

    # Type
    "TIPO CAMBIO": "tipo_cambio",

    # Implementation dates
    "FEC. HORA. INI. IMPL": "inicio_impl",
    "FEC .HORA. FIN. IMPL": "fin_impl",

    # Ratification dates
    # ADR-007: FIN_RATI is the ONLY ratification end reference for KPIs.
    # ADR-008: "FEC. HORA. FIN. RATI. TOTAL" is read ONLY to expose it as an
    #          informational field inside window.ChangeOpsActions. It never
    #          participates in KPIs or business rules.
    "FEC. HORA. INI. RATI": "inicio_rati",
    "FEC. HORA. FIN. RATI": "fin_rati",
    "FEC. HORA. FIN. RATI. TOTAL": "fin_rati_total",

    # Reversion: ADR-007 — the reversions KPI is sourced from JIRA in the
    # future; the engine does NOT read reversion columns from Excel.

    # Responsible / Resource
    "RECURSO": "recurso",            # Pool resource (e.g. "Pool AgileOps Prod")
    "RECURSO ASIGNADO": "responsable",  # Person assigned
    "NOMB/CELL CONTACTO IMPL": "contacto_impl",
    "NOMB/CELL CONTACTO RATI": "contacto_rati",

    # Towers
    "TORRES REQUERIDAS": "torres_requeridas",
    "TORRES COORDINADAS": "torres_coordinadas",

    # Status
    "ESTADO ACTUAL": "estado",

    # Metadata
    "FECHA DE REGISTRO": "fecha_registro",
    "IMPACTA OOR": "impacta_oor",
    "REQUIERE USUARIO ROOT": "requiere_root",
}

# Internal field names required for a valid row
REQUIRED_FIELDS = [
    "ticket",
    "inicio_impl",
    "fin_impl",
    "recurso",
    "estado",
]

# Date columns that need datetime parsing
# (ADR-007: no reversion columns. ADR-008: fin_rati_total parsed for the
#  informational action payload only, never for KPIs.)
DATE_COLUMNS = [
    "inicio_impl",
    "fin_impl",
    "inicio_rati",
    "fin_rati",
    "fin_rati_total",
    "fecha_registro",
]

# ---------------------------------------------------------------
# Operational pool scope — SINGLE SOURCE OF TRUTH
# ---------------------------------------------------------------

# Display pool family → the RECURSO values that belong to it.
# The values are verbatim from the workbook: spacing and case are inconsistent
# on purpose ("POOL S&F-DERIVADO" vs "Pool AgileOps ORO - Derivado").
#
# The ORDER of this tuple IS the display order and is published to the web
# layer as meta.poolOrder, so the frontend never hardcodes the list again.
_POOL_FAMILY_RESOURCES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Yape", ("POOL - YAPE", "POOL - YAPE-DERIVADO")),
    ("S&F", ("Pool S&F", "POOL S&F-DERIVADO")),
    ("AgileOps ORO", ("Pool AgileOps ORO", "Pool AgileOps ORO - Derivado")),
    ("AgileOps Prod", ("Pool AgileOps Prod", "Pool AgileOps Prod - Derivado")),
)


def normalize_recurso(value: Any) -> str:
    """
    Upper-case and remove ALL whitespace from a RECURSO value.

    Normalization absorbs spacing/case drift only ("POOL - YAPE" and
    "POOL   YAPE" are the same value). It does NOT touch hyphens, so
    "Pool AgileOps Prod" never collapses onto a hypothetical
    "POOL-AGILEOPS-PROD".
    """
    return "".join(str(value if value is not None else "").upper().split())


# Display order of the pool families — emitted as meta.poolOrder.
POOL_FAMILY_ORDER: tuple[str, ...] = tuple(
    family for family, _ in _POOL_FAMILY_RESOURCES
)

# The 8 in-scope RECURSO values, flattened from the family table above.
IN_SCOPE_RECURSO: tuple[str, ...] = tuple(
    recurso
    for _, recursos in _POOL_FAMILY_RESOURCES
    for recurso in recursos
)

# Exact-match inclusion whitelist (normalized). NO substring matching:
# this is what keeps AUTOMATIZADO, AUTOMATIZADO ITSM and INFRAESTRUCTURA out.
IN_SCOPE_POOL_KEYS: frozenset[str] = frozenset(
    normalize_recurso(recurso) for recurso in IN_SCOPE_RECURSO
)

# Inverse index: normalized resource key → display family.
_RESOURCE_TO_FAMILY: dict[str, str] = {
    normalize_recurso(recurso): family
    for family, recursos in _POOL_FAMILY_RESOURCES
    for recurso in recursos
}

# Ordered loose tokens, used for FAMILY RESOLUTION ONLY — never for inclusion.
# AGILEOPSORO / AGILEOPSPROD are strictly longer than AGILEOPS and are
# evaluated in family order, so resolution never collapses onto "AGILEOPS"
# alone and can never steal one family from another.
_FAMILY_TOKENS: tuple[tuple[str, str], ...] = (
    ("Yape", "YAPE"),
    ("S&F", "S&F"),
    ("AgileOps ORO", "AGILEOPSORO"),
    ("AgileOps Prod", "AGILEOPSPROD"),
)

# Date format in the Excel (DD/MM/YYYY HH:MM)
EXCEL_DATE_FORMAT = "%d/%m/%Y %H:%M"


def map_columns(df) -> dict[str, str]:
    """
    Map Excel column names to internal names.

    Returns a dict of {excel_col: internal_name} for columns that exist.
    """
    mapped = {}
    for excel_col, internal in COLUMN_MAP.items():
        if excel_col in df.columns:
            mapped[excel_col] = internal
    return mapped


def is_in_scope_pool(recurso: Any) -> bool:
    """
    True when the RECURSO value belongs to the operational pool scope.

    EXACT match on the normalized value — never a substring match. A loose
    match would pull AUTOMATIZADO / AUTOMATIZADO ITSM / INFRAESTRUCTURA into
    the universe, which is exactly the bug this scope guards against.
    """
    return normalize_recurso(recurso) in IN_SCOPE_POOL_KEYS


def get_pool_name(recurso: Any) -> str:
    """
    Resolve a RECURSO value to its display pool family.

    "POOL - YAPE"                          → "Yape"
    "Pool S&F" / "POOL S&F-DERIVADO"        → "S&F"   (one family, no space)
    "Pool AgileOps ORO - Derivado"         → "AgileOps ORO"
    "Pool AgileOps Prod"                   → "AgileOps Prod"

    The DERIVADO distinction stays in get_bar_type(), NOT in the pool name.
    """
    key = normalize_recurso(recurso)
    if not key:
        return "Unknown"

    family = _RESOURCE_TO_FAMILY.get(key)
    if family is not None:
        return family

    # Family-resolution fallback for a new spelling variant of an in-scope
    # pool: resolve it to its family instead of leaking a raw value or
    # "Unknown" into the contract. Inclusion is decided elsewhere
    # (is_in_scope_pool) and is always an exact match.
    for family, token in _FAMILY_TOKENS:
        if token in key:
            return family

    return str(recurso).title()
