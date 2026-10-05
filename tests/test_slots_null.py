"""P06: un slot obligatorio devuelto por el LLM como null cuenta como faltante → clarify, no confirm (hallazgo del eval real, 5 oct)."""
from agent.handle import handle, runtime


class _LLMNull:
    """Understand devuelve la clave obligatoria con null, como hace llama-3.3-70b con '¿Califico?'."""

    def complete(self, prompt, schema=None, *, model="main"):
        task = (schema or {}).get("task") if isinstance(schema, dict) else None
        if task == "understand":
            return {"intent": "eligibility_simulation", "intent_confidence": 0.9, "language": "es", "slots": {"product_type": None}, "guardrail_hits": []}
        if task == "verify":
            return {"ok": True, "notes": []}
        return {"reply": prompt}


def test_slot_null_pide_aclaracion(settings, deps, users):
    d = deps.__class__(**{**deps.__dict__, "llm": _LLMNull()})
    r = handle("¿Califico?", users["cliente_co_ok"], rt=runtime(settings, d))
    assert r["action"] == "clarify" and "P06" in r["_state"]["rules_fired"]


def test_slot_lleno_confirma(settings, deps, users):
    class _LLMFull(_LLMNull):
        def complete(self, prompt, schema=None, *, model="main"):
            r = super().complete(prompt, schema, model=model)
            if "slots" in r:
                r["slots"] = {"product_type": "personal_loan"}
            return r
    d = deps.__class__(**{**deps.__dict__, "llm": _LLMFull()})
    r = handle("¿Califico para un préstamo personal?", users["cliente_co_ok"], rt=runtime(settings, d))
    assert r["action"] == "confirm" and "P02" in r["_state"]["rules_fired"]
