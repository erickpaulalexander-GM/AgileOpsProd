"""
Tests for the operational table scope: resource whitelist, state exclusion,
live-work temporal filter, and updatedAt from the Excel file mtime.

The resource whitelist is sourced from column_map (single source of truth).
The exhaustive whitelist / rejection matrix lives in test_pool_scope.py;
this module pins the TABLE behavior on top of it.
"""
import os
from datetime import datetime, timedelta

from adapter import (
    build_operational_table,
    is_operational_resource,
    is_table_state_allowed,
)
from main import file_mtime_iso


# ---------------------------------------------------------------
# Resource whitelist (exact match on the normalized value)
# ---------------------------------------------------------------
def test_operational_resources_included():
    for recurso in [
        "POOL - YAPE",
        "POOL - YAPE-DERIVADO",
        "Pool S&F",
        "POOL S&F-DERIVADO",
        "Pool AgileOps ORO",
        "Pool AgileOps ORO - Derivado",
        "Pool AgileOps Prod",
        "Pool AgileOps Prod - Derivado",
    ]:
        assert is_operational_resource(recurso), recurso


def test_operational_resources_space_normalization():
    # Whitespace is removed and case is folded, but nothing else is:
    # hyphens are part of the value and must not be invented or dropped.
    assert is_operational_resource("POOL   -   YAPE")
    assert is_operational_resource("pool - yape-derivado")
    assert is_operational_resource("POOLS&F")
    assert is_operational_resource("POOL S&F-DERIVADO")
    assert is_operational_resource("pool   agileops   oro - derivado")
    assert is_operational_resource("  pool agileops prod  ")


def test_operational_resources_excluded():
    for recurso in [
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
        "",
        None,
    ]:
        assert not is_operational_resource(recurso), recurso


def test_pool_sf_is_in_scope():
    """Pool S&F was OUT of scope in ChangeOpsConsole; it is IN here.

    Both spellings ("Pool S&F" and "POOL S&F-DERIVADO") are one family.
    """
    assert is_operational_resource("Pool S&F")
    assert is_operational_resource("POOL S&F-DERIVADO")


# ---------------------------------------------------------------
# State exclusion
# ---------------------------------------------------------------
def test_excluded_states():
    for estado in [
        "Rechazado por Gestor de cambio",
        "Rechazado",
        "Pre Registrado",
        "Registrado",
        "Aprobado LT",
        "Aprobado CL QA",
        "Aprobado CL DEV",
        "Aprobado PO",
    ]:
        assert not is_table_state_allowed(estado), estado


def test_allowed_states():
    for estado in [
        "Coordinado",
        "Cerrado",
        "Pase en curso",
        "Terminado Satisfactorio",
        "Preaprobado",
        "Ratificación parcial en curso",
        "Inicio atrasado",
    ]:
        assert is_table_state_allowed(estado), estado


# ---------------------------------------------------------------
# Table build
# ---------------------------------------------------------------
def _row(ticket, recurso, estado, hour, minute=0):
    start = datetime(2026, 9, 11, hour, minute)
    end = start + timedelta(hours=1)
    return {
        "ticket": ticket,
        "descripcion": "Cambio " + ticket,
        "nombre_app": "APP-" + ticket,
        "responsable": "Resp " + ticket,
        "recurso": recurso,
        "estado": estado,
        "inicio_impl": start,
        "fin_impl": end,
    }


def test_build_operational_table_filters_and_sorts():
    rows = [
        _row("T-20", "Pool AgileOps Prod", "Coordinado", 20),
        _row("T-14", "Pool AgileOps Prod", "Coordinado", 14),
        _row("T-15", "POOL - YAPE", "Pase en curso", 15),
        _row("T-REJ", "Pool AgileOps Prod", "Registrado", 15),   # excluded state
        _row("T-CER", "Pool AgileOps Prod", "Cerrado", 16),      # excluded state
        _row("T-OTRO", "AUTOMATIZADO", "Coordinado", 16),        # excluded resource
    ]
    table = build_operational_table(rows, datetime(2026, 9, 11, 13, 0))

    # Only ACTIVE operational states, sorted by start
    assert [e["ticket"] for e in table] == ["T-14", "T-15", "T-20"]
    assert table[1]["status"] == "Pase en curso"
    # the pool column carries the FAMILY name, not the raw RECURSO value
    assert table[0]["pool"] == "AgileOps Prod"
    assert table[1]["pool"] == "Yape"
    # dates rendered as DD/MM HH:MM
    assert table[0]["inicio_impl"] == "11/09 14:00"
    assert table[2]["inicio_impl"] == "11/09 20:00"


def test_table_only_active_states():
    """The table keeps only Coordinado / Pase en curso."""
    rows = [
        _row("A", "Pool S&F", "Coordinado", 9),
        _row("B", "Pool S&F", "Pase en curso", 10),
        _row("C", "Pool S&F", "Terminado Satisfactorio", 9),
        _row("D", "Pool S&F", "Cerrado", 9),
        _row("E", "Pool S&F", "Preaprobado", 9),
        _row("F", "Pool S&F", "Registrado", 9),
    ]
    table = build_operational_table(rows, datetime(2026, 9, 11, 13, 0))
    assert {e["ticket"] for e in table} == {"A", "B"}


def test_build_operational_table_keeps_columns():
    table = build_operational_table(
        [_row("T1", "Pool AgileOps ORO", "Coordinado", 16)],
        datetime(2026, 9, 11, 13, 0),
    )
    assert set(table[0]) == {
        "responsable", "pool", "type", "ticket", "nombre_app",
        "status", "inicio_impl", "fin_impl",
    }


def test_build_operational_table_empty():
    assert build_operational_table([], datetime(2026, 9, 11, 13, 0)) == []


def test_build_operational_table_includes_out_of_window():
    # The table is the operational universe, not the timeline window.
    rows = [
        _row("T-early", "Pool AgileOps Prod", "Coordinado", 2),   # before window
        _row("T-late", "POOL - YAPE", "Coordinado", 23),          # after window
    ]
    table = build_operational_table(rows, datetime(2026, 9, 11, 13, 0))
    assert [e["ticket"] for e in table] == ["T-early", "T-late"]
    assert table[0]["inicio_impl"] == "11/09 02:00"
    assert table[1]["inicio_impl"] == "11/09 23:00"


def test_table_name_is_nombre_app():
    """The table carries NOMBRE APP (nombre_app), not the change description."""
    table = build_operational_table(
        [_row("T1", "Pool AgileOps Prod", "Coordinado", 16)],
        datetime(2026, 9, 11, 13, 0),
    )
    assert table[0]["nombre_app"] == "APP-T1"


def test_derivado_stays_in_the_type_column_not_the_pool():
    """DERIVADO is the bar TYPE; the pool family is the same as its base pool."""
    rows = [
        _row("BASE", "Pool AgileOps Prod", "Coordinado", 9),
        _row("DERIV", "Pool AgileOps Prod - Derivado", "Coordinado", 10),
    ]
    table = build_operational_table(rows, datetime(2026, 9, 11, 13, 0))
    by_ticket = {e["ticket"]: e for e in table}
    assert by_ticket["BASE"]["type"] == "Implementación"
    assert by_ticket["DERIV"]["type"] == "Derivado"
    assert by_ticket["BASE"]["pool"] == by_ticket["DERIV"]["pool"] == "AgileOps Prod"


def test_temporal_filter_keeps_live_work_only():
    """Drop implementations already finished before the reference."""
    rows = [
        _row("FUT", "Pool AgileOps Prod", "Coordinado", 20),   # 20:00-21:00 -> live
        _row("DONE", "Pool AgileOps Prod", "Coordinado", 10),  # 10:00-11:00 -> finished
    ]
    ref = datetime(2026, 9, 11, 15, 0)
    table = build_operational_table(
        rows, datetime(2026, 9, 11, 13, 0), reference_dt=ref
    )
    assert [e["ticket"] for e in table] == ["FUT"]


def test_temporal_filter_keeps_boundary():
    """fin_impl == reference_dt is kept (>=)."""
    rows = [_row("BOUND", "Pool AgileOps Prod", "Coordinado", 14)]  # 14:00-15:00
    ref = datetime(2026, 9, 11, 15, 0)
    table = build_operational_table(
        rows, datetime(2026, 9, 11, 13, 0), reference_dt=ref
    )
    assert [e["ticket"] for e in table] == ["BOUND"]


def test_temporal_filter_none_keeps_all():
    rows = [_row("DONE", "Pool AgileOps Prod", "Coordinado", 10)]
    table = build_operational_table(
        rows, datetime(2026, 9, 11, 13, 0), reference_dt=None
    )
    assert len(table) == 1


# ---------------------------------------------------------------
# updatedAt from file mtime
# ---------------------------------------------------------------
def test_file_mtime_iso(tmp_path):
    f = tmp_path / "ControlPases.xlsx"
    f.write_bytes(b"x")
    ts = 1_760_000_000
    os.utime(f, (ts, ts))
    assert file_mtime_iso(f) == datetime.fromtimestamp(ts).strftime("%Y-%m-%dT%H:%M:%S")


if __name__ == "__main__":
    test_operational_resources_included()
    test_operational_resources_space_normalization()
    test_operational_resources_excluded()
    test_pool_sf_is_in_scope()
    test_excluded_states()
    test_allowed_states()
    test_build_operational_table_filters_and_sorts()
    test_build_operational_table_keeps_columns()
    test_build_operational_table_empty()
    print("All operational-table tests passed (mtime test needs pytest tmp_path).")