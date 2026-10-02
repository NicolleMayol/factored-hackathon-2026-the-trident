"""Adaptador real (trace_mlflow). Se implementa en el bloque de integración (checklist ADR-21); misma interfaz que el mock."""
from __future__ import annotations


class TraceMlflow:
    def __init__(self, *a, **k):
        raise NotImplementedError("trace_mlflow: pendiente de integración; usa AGENT_*=mock en local")
