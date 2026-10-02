"""Adaptador real (llm_fmapi). Se implementa en el bloque de integración (checklist ADR-21); misma interfaz que el mock."""
from __future__ import annotations


class LLMFmApi:
    def __init__(self, *a, **k):
        raise NotImplementedError("llm_fmapi: pendiente de integración; usa AGENT_*=mock en local")
