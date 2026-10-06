"""
T3 — pool scope as a SINGLE source of truth.

The pool list lives once, in column_map.py; adapter.py imports it. These
tests pin:

- the exact-match whitelist (8 RECURSO values) — a substring implementation
  must NOT pass, so AUTOMATIZADO / AUTOMATIZADO ITSM / INFRAESTRUCTURA stay out;
- the ordered family resolution to the 4 display pools;
- the whitelist and the family table agree with each other;
- meta.poolOrder is emitted from Python even with zero bars in the window.
"""
from datetime import datetime
from pathlib import Path

import adapter
import column_map
from adapter import compute_window, to_contract
from column_map import (
    POOL_FAMILY_ORDER,
    get_pool_name,
    is_in_scope_pool,
    normalize_recurso,
)

PYTHON_DIR = Path(__file__).resolve().parent.parent / "python"

# The 8 in-scope RECURSO values, verbatim from the workbook.
IN_SCOPE = [
    "POOL - YAPE",
    "POOL - YAPE-DERIVADO",
    "Pool S&F",
    "POOL S&F-DERIVADO",
    "Pool AgileOps ORO",
    "Pool AgileOps ORO - Derivado",
    "Pool AgileOps Prod",
    "Pool AgileOps Prod - Derivado",
]

# Out-of-scope RECURSO values that must stay excluded.
OUT_OF_SCOPE = [
    "INFRAESTRUCTURA",
    "AUTOMATIZADO",
    "AUTOMATIZADO ITSM",
    "EXPRESS AUTOMATICO",
    "DC_CONNECTIVITY(TELECOM)",
    "CyberSOC",
    "EU_NETWORKING",
    "OPERACIONES DATA",
    "SelfServices APIG",
    "SelfServices AGIL",
]


# ---------------------------------------------------------------
# Shape of the single source of truth
# ---------------------------------------------------------------
def test_scope_has_exactly_eight_resource_values():
    assert set(column_map.IN_SCOPE_RECURSO) == set(IN_SCOPE)
    assert len(column_map.IN_SCOPE_RECURSO) == 8


def test_pool_order_is_the_canonical_display_order():
    assert POOL_FAMILY_ORDER == ("Yape", "S&F", "AgileOps ORO", "AgileOps Prod")


def test_normalization_folds_case_and_removes_all_whitespace():
    assert normalize_recurso("Pool AgileOps ORO - Derivado") == "POOLAGILEOPSORO-DERIVADO"
    assert normalize_recurso("POOL S&F-DERIVADO") == "POOLS&F-DERIVADO"
    assert normalize_recurso("  pool   -   yape  ") == "POOL-YAPE"
    assert normalize_recurso("") == ""
    assert normalize_recurso(None) == ""


# ---------------------------------------------------------------
# Inclusion: exact value after normalization
# ---------------------------------------------------------------
def test_whitelist_accepts_all_eight_values():
    for recurso in IN_SCOPE:
        assert is_in_scope_pool(recurso), recurso


def test_whitelist_accepts_spacing_and_case_variants():
    accepted = [
        "POOL   -   YAPE",
        "pool - yape-derivado",
        "  Pool S&F  ",
        "POOLS&F",
        "pool   s&f-derivado",
        "POOLAGILEOPSORO",
        "Pool   AgileOps   ORO   -   Derivado",
        "pool agileops prod",
        "Pool  AgileOps  Prod  -  Derivado",
    ]
    for recurso in accepted:
        assert is_in_scope_pool(recurso), recurso


def test_whitelist_does_not_fold_hyphens():
    """Normalization removes whitespace only — hyphens are part of the value."""
    # "POOL S&F-DERIVADO" has NO space before the hyphen of "-DERIVADO":
    assert is_in_scope_pool("POOLAGILEOPSPROD-DERIVADO")
    assert is_in_scope_pool("POOL-YAPE-DERIVADO")
    # ...while "POOL - YAPE" does, and both normalizations must be stable:
    assert normalize_recurso("POOL - YAPE") == "POOL-YAPE"
    assert is_in_scope_pool("POOL-YAPE")
    # Inventing a hyphen where the value has none is a different value:
    assert not is_in_scope_pool("POOL-AGILEOPS-PROD")
    assert not is_in_scope_pool("POOL-AGILEOPS-ORO")


def test_whitelist_rejects_every_out_of_scope_value():
    for recurso in OUT_OF_SCOPE:
        assert not is_in_scope_pool(recurso), recurso


def test_whitelist_rejects_empty_and_missing_values():
    for valor in ["", "   ", None, "nan"]:
        assert not is_in_scope_pool(valor), valor


def test_substring_lookalikes_are_rejected():
    """A substring implementation would accept these — exact matching must not.

    AUTOMATIZADO / AUTOMATIZADO ITSM are the two that a substring match on a
    pool token would wrongly pull into the operational universe.
    """
    for candidato in [
        "AUTOMATIZADO",
        "AUTOMATIZADO ITSM",
        "INFRAESTRUCTURA YAPE",
        "POOL AGILEOPS",
        "AUTOMATIZADO - POOL - YAPE",
        "POOL AGILEOPS PROD - DERIVADO (LEGACY)",
    ]:
        assert not is_in_scope_pool(candidato), candidato


# ---------------------------------------------------------------
# Family resolution
# ---------------------------------------------------------------
def test_family_resolution_for_all_eight_values():
    expected = {
        "POOL - YAPE": "Yape",
        "POOL - YAPE-DERIVADO": "Yape",
        "Pool S&F": "S&F",
        "POOL S&F-DERIVADO": "S&F",
        "Pool AgileOps ORO": "AgileOps ORO",
        "Pool AgileOps ORO - Derivado": "AgileOps ORO",
        "Pool AgileOps Prod": "AgileOps Prod",
        "Pool AgileOps Prod - Derivado": "AgileOps Prod",
    }
    for recurso, familia in expected.items():
        assert get_pool_name(recurso) == familia, recurso


def test_family_resolution_is_whitespace_and_case_insensitive():
    assert get_pool_name("POOL S&F-DERIVADO") == "S&F"
    assert get_pool_name("  pool   s&f  ") == "S&F"
    assert get_pool_name("Pool AgileOps ORO - Derivado") == "AgileOps ORO"
    assert get_pool_name("POOLAGILEOPSORO") == "AgileOps ORO"
    assert get_pool_name("pool   agileops   prod-derivado") == "AgileOps Prod"


def test_family_resolution_never_relies_on_agileops_alone():
    """AGILEOPSORO must be resolved before any looser AGILEOPS token."""
    assert get_pool_name("Pool AgileOps ORO") == "AgileOps ORO"
    # A bare AGILEOPS token belongs to no family.
    assert get_pool_name("POOL AGILEOPS") not in ("AgileOps ORO", "AgileOps Prod")


def test_every_in_scope_value_resolves_to_a_known_family():
    for recurso in column_map.IN_SCOPE_RECURSO:
        assert get_pool_name(recurso) in POOL_FAMILY_ORDER, recurso


def test_unknown_resource_does_not_leak_unknown():
    assert get_pool_name("INFRAESTRUCTURA") not in POOL_FAMILY_ORDER
    assert get_pool_name("INFRAESTRUCTURA") != "Unknown"


def test_empty_resource_falls_back_to_unknown():
    assert get_pool_name("") == "Unknown"
    assert get_pool_name(None) == "Unknown"


# ---------------------------------------------------------------
# meta.poolOrder
# ---------------------------------------------------------------
def test_meta_pool_order_is_emitted_in_display_order():
    rows = [
        {
            "ticket": "T1",
            "nombre_app": "APP",
            "responsable": "Ana",
            "recurso": "Pool AgileOps ORO",
            "estado": "Coordinado",
            "inicio_impl": datetime(2026, 9, 11, 9, 0),
            "fin_impl": datetime(2026, 9, 11, 10, 0),
        }
    ]
    window = compute_window(datetime(2026, 9, 11, 8, 30))
    contract = to_contract(rows, {}, window)
    assert contract["meta"]["poolOrder"] == ["Yape", "S&F", "AgileOps ORO", "AgileOps Prod"]


def test_meta_pool_order_lists_all_families_with_zero_bars():
    """All 4 names are emitted even when no pool has bars in the window."""
    window = compute_window(datetime(2026, 9, 11, 8, 30))
    contract = to_contract([], {}, window)
    assert contract["timeline"] == []
    assert contract["meta"]["poolOrder"] == ["Yape", "S&F", "AgileOps ORO", "AgileOps Prod"]


# ---------------------------------------------------------------
# Single source of truth
# ---------------------------------------------------------------
def test_adapter_whitelist_is_the_column_map_whitelist():
    assert adapter.OPERATIONAL_RESOURCES == frozenset(column_map.IN_SCOPE_POOL_KEYS)
    for recurso in IN_SCOPE:
        assert adapter.is_operational_resource(recurso), recurso
    for recurso in OUT_OF_SCOPE:
        assert not adapter.is_operational_resource(recurso), recurso


def test_adapter_normalization_is_the_column_map_normalization():
    assert adapter._norm_key is column_map.normalize_recurso


def test_adapter_source_does_not_duplicate_the_pool_list():
    """No pool literal may live outside column_map.py."""
    src = (PYTHON_DIR / "adapter.py").read_text(encoding="utf-8")
    for literal in column_map.IN_SCOPE_RECURSO:
        assert literal not in src, literal