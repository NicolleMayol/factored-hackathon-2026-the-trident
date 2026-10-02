"""Punto de entrada del agente: handle(message, session) → respuesta de contracts/api.yaml. Sin cargar modelos al importar."""
from __future__ import annotations
import time
import uuid
from functools import lru_cache
from typing import Any

from agent.adapters import Deps, build_deps
from agent.config.settings import Settings, get_settings
from agent.graph.build import build_graph

_PENDING: dict[str, dict[str, Any]] = {}   # action_id → estado pendiente de confirmación (TTL 10 min). En Azure vive en Cosmos conversations.


@lru_cache(maxsize=1)
def _runtime() -> tuple[Settings, Deps, Any]:
    s = get_settings()
    d = build_deps(s)
    return s, d, build_graph(d, s)


def runtime(settings: Settings | None = None, deps: Deps | None = None):
    if settings is None and deps is None:
        return _runtime()
    s = settings or get_settings()
    d = deps or build_deps(s)
    return s, d, build_graph(d, s)


def handle(message: str, session: dict[str, Any], *, rt=None, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """session: {customer_id, scopes, locale, conversation_id?, trace_id?}. Devuelve {reply, action, citations, trace_id, cost_usd, latency_ms, action_id?}."""
    s, d, graph = rt or runtime()
    t0 = time.perf_counter()
    trace_id = session.get("trace_id") or uuid.uuid4().hex
    conv = session.get("conversation_id") or uuid.uuid4().hex
    locale = session.get("locale", "es-MX")
    init = {"trace_id": trace_id, "conversation_id": conv, "customer_id": session["customer_id"], "scopes": list(session.get("scopes", [])),
            "locale": locale, "language": "pt" if locale.startswith("pt") else "es", "message": message, "history": history or [],
            "node_path": [], "iterations": 0, "tool_results": {}, "tools_called": []}
    with d.trace.span("turn", trace_id=trace_id):
        st = graph.invoke(init)
    action_id = None
    if st.get("action") == "confirm":
        action_id = uuid.uuid4().hex[:12]
        _PENDING[action_id] = {"state": st, "ts": time.time(), "conversation_id": conv}
    latency = round((time.perf_counter() - t0) * 1000, 1)
    row = {"ts": time.time(), "trace_id": trace_id, "conversation_id": conv, "locale": locale, "node_path": st.get("node_path"),
           "tools_called": st.get("tools_called"), "rules_fired": st.get("rules_fired"), "expected_action": session.get("expected_action"),
           "action": st.get("action"), "escalate_reason": st.get("escalate_reason", "none"), "guardrail_hits": st.get("guardrail_hits"),
           "groundedness": 1.0 if st.get("verify_ok") else 0.0, "tokens_in": st.get("tokens_in", 0), "tokens_out": st.get("tokens_out", 0),
           "cost_usd": st.get("cost_usd", 0.0), "latency_ms": latency, "prompt_version": st.get("prompt_version"), "model_version": st.get("model_version")}
    d.trace.log_turn(row)
    return {"reply": st.get("reply"), "action": st.get("action"), "citations": [{"type": c["type"], "id": c["id"]} for c in st.get("citations", [])],
            "trace_id": trace_id, "conversation_id": conv, "cost_usd": row["cost_usd"], "latency_ms": latency,
            **({"action_id": action_id} if action_id else {}), **({"case_id": st["case_id"]} if st.get("case_id") else {}),
            "_state": st}


def confirm(action_id: str, confirmed: bool, session: dict[str, Any], *, rt=None) -> dict[str, Any] | None:
    """POST /chat/confirm: ejecuta la pre-evaluación ya autorizada. Nuevo trace_id, misma conversación."""
    p = _PENDING.pop(action_id, None)
    if not p or time.time() - p["ts"] > 600 or p["state"]["customer_id"] != session["customer_id"]:
        return None
    s, d, graph = rt or runtime()
    st = p["state"]
    if not confirmed:
        return {"reply": {"es": "Entendido, no haré la pre-evaluación.", "pt": "Entendido, não farei a pré-avaliação."}[st.get("language", "es")],
                "action": "answer", "citations": [], "trace_id": uuid.uuid4().hex, "conversation_id": p["conversation_id"]}
    from agent.graph.nodes import Nodes
    n = Nodes(d, s)
    st2 = n.respond({**st, "_confirmed": True, "trace_id": uuid.uuid4().hex})
    return {"reply": st2["reply"], "action": "answer", "citations": [{"type": c["type"], "id": c["id"]} for c in st.get("citations", [])],
            "trace_id": st2["trace_id"], "conversation_id": p["conversation_id"]}


def healthz(*, rt=None) -> tuple[int, dict[str, str]]:
    """200 con ok|cold|down por dependencia; 503 solo si llm o cosmos están down. Sin nombres internos (api.yaml v1.2)."""
    s, d, _ = rt or runtime()
    h = {k: d.health.get(k, "down") for k in ("llm", "cosmos", "prescore", "embed", "sql")}
    status = 503 if h["llm"] == "down" or h["cosmos"] == "down" else 200
    return status, h
