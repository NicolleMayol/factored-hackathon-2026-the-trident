"""Adaptador real (embed_serving). Se implementa en el bloque de integración (checklist ADR-21); misma interfaz que el mock."""
from __future__ import annotations


class EmbedServing:
    def __init__(self, *a, **k):
        raise NotImplementedError("embed_serving: pendiente de integración; usa AGENT_*=mock en local")
