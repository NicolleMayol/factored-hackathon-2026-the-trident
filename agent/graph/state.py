"""Estado del grafo. Los campos del handoff (contracts/handoff.schema.json) están desde el primer commit."""
from __future__ import annotations
from typing import Any, Literal, TypedDict

Action = Literal["answer", "clarify", "confirm", "escalate", "blocked", "reject"]
EscalateReason = Literal["policy", "scope", "no_citation", "timeout_tool", "guardrail", "none"]


class Citation(TypedDict):
    type: Literal["chunk", "rule", "tool"]
    id: str
    text: str


class AgentState(TypedDict, total=False):
    # entrada
    trace_id: str
    conversation_id: str
    customer_id: str
    scopes: list[str]
    locale: str          # es-MX | es-CO | es-AR | pt-BR
    language: str        # es | pt
    country: str         # MX | CO | AR
    message: str
    history: list[dict[str, str]]
    # Understand
    intent: str
    intent_confidence: float
    slots: dict[str, Any]
    guardrail_hits: list[str]
    # Decide
    action: Action
    rules_fired: list[str]
    reason_code: str
    allowed_tools: list[str]
    # Act
    tool_results: dict[str, Any]
    tools_called: list[str]
    iterations: int
    # Verify
    verified_facts: list[dict[str, str]]
    citations: list[Citation]
    verify_ok: bool
    verify_notes: list[str]
    # Escalate / Respond
    escalate_reason: EscalateReason
    case_id: str
    reply: str
    pending_action_id: str
    # telemetría
    node_path: list[str]
    cost_usd: float
    tokens_in: int
    tokens_out: int
    prompt_version: str
    model_version: str
    # internos (prefijo _): no salen en la respuesta ni en el handoff
    _policy_action: str
    _mixed_language: bool
    _profile: dict[str, Any]
    _products: list[dict[str, Any]]
    _cold_used: list[str]
    _confirmed: bool
