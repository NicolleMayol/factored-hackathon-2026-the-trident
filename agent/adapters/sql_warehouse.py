"""Adaptador real (sql_warehouse). Se implementa en el bloque de integración (checklist ADR-21); misma interfaz que el mock."""
from __future__ import annotations


class SQLWarehouse:
    def __init__(self, *a, **k):
        raise NotImplementedError("sql_warehouse: pendiente de integración; usa AGENT_*=mock en local")
