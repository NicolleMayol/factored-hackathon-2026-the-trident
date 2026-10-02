"""Adaptador real (store_cosmos). Se implementa en el bloque de integración (checklist ADR-21); misma interfaz que el mock."""
from __future__ import annotations


class StoreCosmos:
    def __init__(self, *a, **k):
        raise NotImplementedError("store_cosmos: pendiente de integración; usa AGENT_*=mock en local")
