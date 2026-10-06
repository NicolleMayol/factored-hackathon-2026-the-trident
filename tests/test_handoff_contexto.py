"""El caso que escala en Decide (p. ej. P07 por mora) llega al analista con hechos, regla y señal de riesgo, no vacío."""
from agent import handle as H
from agent.cli import USERS
from agent.handoff import build_handoff, validate_handoff


def _caso(user, msg):
    u = USERS[user]
    out = H.handle(msg, {"customer_id": u["customer_id"], "scopes": u["scopes"], "locale": u["locale"]})
    _, d, _ = H.runtime()
    return out, d.store.get_handoff(out["case_id"])


def test_escalamiento_por_riesgo_trae_contexto():
    out, doc = _caso("cliente_ar_no", "¿Califico para un préstamo personal?")
    assert out["action"] == "escalate" and doc["reason_code"] == "risk_flag"
    validate_handoff(doc)
    assert any(f["source"] == "gold.customer_products" and "mora máxima" in f["fact"] for f in doc["verified_facts"])
    assert any(e["type"] == "rule" and e["id"] == "P07" and "days_past_due" in e["text"] for e in doc["evidence"])
    assert any(r.startswith("days_past_due=") for r in doc["risk_flags"])


def test_sin_estado_de_decide_el_paquete_sigue_valido():
    doc = build_handoff({"customer_id": "TEST-CO-001", "trace_id": "t", "message": "hola"}, "out_of_scope")
    validate_handoff(doc)
    assert doc["verified_facts"] == [] and doc["evidence"] == [] and doc["risk_flags"] == []
