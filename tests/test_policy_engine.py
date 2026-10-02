"""Una prueba por regla P01–P11 y por banda (libre / condicionada / cerrada)."""
import pytest
from agent.policy import engine

POL = "policy/policy.yaml"
BASE = {"intent": "product_info", "intent_confidence": 0.9, "scopes": ["customer:read", "credit:simulate"], "jwt_valid": True}


def d(**kw):
    return engine.decide({**BASE, **kw}, POL)


def test_P01_product_info_auto():
    r = d(); assert r.action == "auto" and "P01" in r.rules_fired and "search_policy" in r.allowed_tools


def test_P02_simulation_confirm():
    r = d(intent="eligibility_simulation"); assert r.action == "confirm" and "evaluate_eligibility" in r.allowed_tools


def test_P02_sin_scope_no_aplica():
    r = d(intent="eligibility_simulation", scopes=["customer:read"]); assert r.action == "escalate" and "P02" not in r.rules_fired


def test_P03_formal_application_escalate():
    r = d(intent="formal_application"); assert r.action == "escalate" and r.reason_code == "regulatory"


def test_P04_disbursement_escalate():
    assert d(intent="disbursement").reason_code == "regulatory"


def test_P05_borderline():
    r = d(intent="eligibility_simulation", prescore_ci_crosses_threshold=True); assert r.action == "escalate" and r.reason_code == "borderline"


def test_P06_clarify_una_vez_luego_escala():
    assert d(missing_required_slots=True).action == "clarify"
    assert d(missing_required_slots=True, clarifications=1).action == "escalate"


def test_P07_risk_flag_gana_a_auto():
    r = d(days_past_due=5); assert r.action == "escalate" and r.reason_code == "risk_flag"
    assert d(customer_status="Suspended").action == "escalate"


def test_P08_out_of_scope_abstain():
    assert d(intent="out_of_scope").action == "abstain"


def test_P09_baja_confianza_clarify():
    assert d(intent_confidence=0.4).action == "clarify"
    assert d(mixed_language=True).action == "clarify"


def test_P10_injection_block_gana_a_todo():
    r = d(injection_detected=True); assert r.action == "block" and r.reason_code == "injection_suspected"


def test_P11_jwt_invalid_reject():
    assert d(jwt_invalid=True).action == "reject"


def test_default_escalate_out_of_scope():
    r = engine.decide({"intent": "algo_raro", "intent_confidence": 0.9, "scopes": []}, POL); assert r.action == "escalate" and r.reason_code == "out_of_scope"


def test_condicion_sin_mapeo_falla_rapido():
    with pytest.raises(ValueError):
        engine._eval_condition("algo_nuevo", {})


# ---- elegibilidad (bandas)
CAT = "data/mock/catalog.yaml"


def test_banda_libre_elegible():
    r = engine.evaluate_eligibility({"credit_score": 780, "customer_status": "Active", "estimated_monthly_income": 9500000}, {"max_days_past_due": 0}, "personal_loan", 5000000, {"ci_low": 0.7, "ci_high": 0.9}, "CO", CAT, [])
    assert r["outcome"] == "Elegible" and r["rules_fired"] == []


def test_banda_cerrada_mora():
    r = engine.evaluate_eligibility({"credit_score": 590, "customer_status": "Active"}, {"max_days_past_due": 45}, "personal_loan", None, None, "AR", CAT, [])
    assert r["outcome"] == "No elegible" and "E02" in r["rules_fired"]


def test_banda_condicionada_ic_cruza_umbral():
    r = engine.evaluate_eligibility({"credit_score": 650, "customer_status": "Active"}, {"max_days_past_due": 0}, "personal_loan", None, {"ci_low": 0.45, "ci_high": 0.6}, "MX", CAT, [])
    assert r["outcome"] == "Revisión humana" and "E09" in r["rules_fired"]


def test_tasa_sobre_tope_regulatorio_va_a_humano():
    r = engine.evaluate_eligibility({"credit_score": 800, "customer_status": "Active"}, {"max_days_past_due": 0}, "credit_card", None, None, "CO", CAT,
                                    [{"country": "CO", "product_type": "credit_card", "rate_kind": "usura", "rate_max": 20.0}])
    assert r["outcome"] == "Revisión humana" and "E11" in r["rules_fired"]


def test_tope_por_pais_cat_mx_y_cft_ar():
    rates = [{"country": "MX", "product_type": "credit_card", "rate_kind": "cat", "rate_max": 30.0}, {"country": "MX", "product_type": "credit_card", "rate_kind": "ea", "rate_max": 80.0},
             {"country": "AR", "product_type": "credit_card", "rate_kind": "cft", "rate_max": 90.0}, {"country": "AR", "product_type": "credit_card", "rate_kind": "tna", "rate_max": 300.0}]
    assert engine.regulatory_cap(rates, "MX", "credit_card") == 30.0
    assert engine.regulatory_cap(rates, "AR", "credit_card") == 90.0
    assert engine.regulatory_cap(rates, "CO", "credit_card") is None
