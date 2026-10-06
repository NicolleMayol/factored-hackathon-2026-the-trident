"""Construcción y validación del paquete de handoff (contracts/handoff.schema.json)."""
from __future__ import annotations
import json
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any
import jsonschema

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "contracts" / "handoff.schema.json"


@lru_cache(maxsize=1)
def _schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_handoff(doc: dict[str, Any]) -> None:
    jsonschema.validate(doc, _schema())


POLICY_PATH = Path(__file__).resolve().parents[1] / "policy" / "policy.yaml"


@lru_cache(maxsize=1)
def _policy_text() -> dict[str, str]:
    """id de regla de política → su condición, para que el analista vea por qué escaló."""
    try:
        import yaml
        rules = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8")).get("rules", [])
        return {r["id"]: str(r.get("condition") or r.get("intent") or "") for r in rules if "id" in r}
    except Exception:  # noqa: BLE001
        return {}


def _decide_context(state: dict[str, Any]) -> tuple[list[dict[str, str]], list[dict[str, str]], list[str]]:
    """Lo que Decide ya sabía cuando escaló antes de llamar tools (p. ej. P07 por mora): hechos, reglas y señales de riesgo.
    Sin esto el caso llegaba vacío al analista. Solo datos que el agente ya leyó del perfil del cliente."""
    facts, rules, risks = [], [], []
    slots = state.get("slots") or {}
    if state.get("intent"):
        facts.append({"fact": f"Intención: {state['intent']}", "source": "understand"})
    if slots.get("product_type"):
        facts.append({"fact": f"Producto pedido: {slots['product_type']}", "source": "understand"})
    if slots.get("amount"):
        facts.append({"fact": f"Monto pedido: {slots['amount']}", "source": "understand"})
    prof, prods = state.get("_profile") or {}, state.get("_products") or []
    if prof.get("customer_status"):
        facts.append({"fact": f"Estado de la cuenta: {prof['customer_status']}", "source": "gold.customer_profile"})
        if prof["customer_status"] != "Active":
            risks.append(f"customer_status={prof['customer_status']}")
    if prods:
        dpd = max(int(p.get("days_past_due") or 0) for p in prods)
        facts.append({"fact": f"Productos: {len(prods)}, mora máxima {dpd} días", "source": "gold.customer_products"})
        if dpd > 0:
            risks.append(f"days_past_due={dpd}")
    txt = _policy_text()
    for r in state.get("rules_fired") or []:
        rules.append({"type": "rule", "id": r, "text": txt.get(r, "")[:300]})
    return facts, rules, risks


def build_handoff(state: dict[str, Any], reason_code: str) -> dict[str, Any]:
    tr = state.get("tool_results", {})
    actions = [{"tool": t, "result": _short(tr.get(t)), "verified": bool(state.get("verify_ok"))} for t in state.get("tools_called", [])]
    evidence = [{"type": c["type"], "id": c["id"], "text": c.get("text", "")[:300]} for c in state.get("citations", [])]
    ctx_facts, ctx_rules, ctx_risks = _decide_context(state)
    facts = list(state.get("verified_facts", []))
    facts += [f for f in ctx_facts if f["fact"] not in {x.get("fact") for x in facts}]
    evidence += [r for r in ctx_rules if r["id"] not in {e["id"] for e in evidence}]
    return {
        "case_id": state.get("case_id") or f"case-{uuid.uuid4().hex[:12]}",
        "customer_id": state["customer_id"],
        "locale": state.get("locale", "es-MX"),
        "reason_code": reason_code,
        "request_summary": (state.get("message") or "")[:600],
        "verified_facts": facts,
        "actions_taken": actions,
        "evidence": evidence,
        "open_questions": state.get("verify_notes", [])[:5],
        "risk_flags": list(state.get("guardrail_hits", [])) + [r for r in ctx_risks if r not in state.get("guardrail_hits", [])],
        "trace_id": state["trace_id"],
    }


def _short(v: Any) -> str:
    s = json.dumps(v, ensure_ascii=False, default=str) if not isinstance(v, str) else v
    return s[:300]
