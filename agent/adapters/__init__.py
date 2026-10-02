"""Adaptadores: una interfaz, dos implementaciones (mock | real), elegidas por AGENT_* (ADR-21)."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Protocol


class LLM(Protocol):
    def complete(self, prompt: str, schema: dict | None = None, *, model: str = "main") -> dict[str, Any]: ...


class SQL(Protocol):
    def query(self, name: str, params: dict[str, Any]) -> list[dict[str, Any]]: ...


class Store(Protocol):
    def search(self, query_vec: list[float], filters: dict[str, Any], k: int = 5) -> list[dict[str, Any]]: ...
    def put_handoff(self, doc: dict[str, Any]) -> None: ...
    def get_handoff(self, case_id: str) -> dict[str, Any] | None: ...


class Embed(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...
    @property
    def model_version(self) -> str: ...


class Prescore(Protocol):
    def predict(self, features: dict[str, Any]) -> dict[str, Any]: ...


class Trace(Protocol):
    def span(self, name: str, **attrs: Any): ...
    def log_turn(self, row: dict[str, Any]) -> None: ...


@dataclass
class Deps:
    llm: LLM
    sql: SQL
    store: Store
    embed: Embed
    prescore: Prescore
    trace: Trace
    health: dict[str, str]  # llm|cosmos|prescore|embed|sql -> ok|cold|down


def build_deps(settings=None) -> Deps:
    """Construye adaptadores según AGENT_*. Importa perezosamente: nada pesado al cargar el paquete."""
    from agent.config.settings import get_settings
    s = settings or get_settings()
    if s.agent_llm == "mock":
        from agent.adapters.llm_mock import LLMMock as L
    else:
        from agent.adapters.llm_fmapi import LLMFmApi as L
    if s.agent_sql == "mock":
        from agent.adapters.sql_csv import SQLCsv as Q
    else:
        from agent.adapters.sql_warehouse import SQLWarehouse as Q
    if s.agent_store == "mock":
        from agent.adapters.store_local import StoreLocal as St
    else:
        from agent.adapters.store_cosmos import StoreCosmos as St
    if s.agent_embed == "mock":
        from agent.adapters.embed_mock import EmbedMock as E
    else:
        from agent.adapters.embed_serving import EmbedServing as E
    if s.agent_prescore == "mock":
        from agent.adapters.prescore_mock import PrescoreMock as P
    else:
        from agent.adapters.prescore_serving import PrescoreServing as P
    if s.agent_trace == "mock":
        from agent.adapters.trace_local import TraceLocal as T
    else:
        from agent.adapters.trace_mlflow import TraceMlflow as T
    embed = E(s)
    return Deps(llm=L(s), sql=Q(s), store=St(s, embed), embed=embed, prescore=P(s), trace=T(s),
                health={"llm": "ok", "cosmos": "ok", "prescore": "ok", "embed": "ok", "sql": "ok"})
