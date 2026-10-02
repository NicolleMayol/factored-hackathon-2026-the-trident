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


def build_handoff(state: dict[str, Any], reason_code: str) -> dict[str, Any]:
    tr = state.get("tool_results", {})
    actions = [{"tool": t, "result": _short(tr.get(t)), "verified": bool(state.get("verify_ok"))} for t in state.get("tools_called", [])]
    evidence = [{"type": c["type"], "id": c["id"], "text": c.get("text", "")[:300]} for c in state.get("citations", [])]
    return {
        "case_id": state.get("case_id") or f"case-{uuid.uuid4().hex[:12]}",
        "customer_id": state["customer_id"],
        "locale": state.get("locale", "es-MX"),
        "reason_code": reason_code,
        "request_summary": (state.get("message") or "")[:600],
        "verified_facts": state.get("verified_facts", []),
        "actions_taken": actions,
        "evidence": evidence,
        "open_questions": state.get("verify_notes", [])[:5],
        "risk_flags": list(state.get("guardrail_hits", [])),
        "trace_id": state["trace_id"],
    }


def _short(v: Any) -> str:
    s = json.dumps(v, ensure_ascii=False, default=str) if not isinstance(v, str) else v
    return s[:300]
