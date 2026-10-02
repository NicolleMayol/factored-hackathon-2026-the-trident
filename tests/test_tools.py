"""Contrato de cada tool (entrada/salida de contracts/tools.yaml) sobre los mocks."""
from agent import tools as T


def test_get_customer_profile_sin_columnas_excluidas(deps):
    r = T.get_customer_profile(deps, "TEST-CO-001")
    assert r["found"] and r["country"] == "Colombia"
    assert not {"gender", "marital_status", "date_of_birth", "document_number"} & set(r)


def test_get_customer_products(deps):
    r = T.get_customer_products(deps, "TEST-AR-003")
    assert len(r["products"]) == 3 and max(p["days_past_due"] for p in r["products"]) == 45


def test_search_policy_filtra_pais_e_idioma(deps):
    r = T.search_policy(deps, "taxa de juros do empréstimo pessoal", "CO", "pt")
    assert r["chunks"] and all(c["chunk_id"].startswith("POL-CO-") and "-pt-" in c["chunk_id"] for c in r["chunks"])
    assert r["embedding_model_version"]


def test_get_prescore_devuelve_banda_no_decision(deps):
    r = T.get_prescore(deps, "TEST-CO-001")
    assert {"probability", "ci_low", "ci_high", "shap_top3", "model_version"} <= set(r)
    assert 0 <= r["ci_low"] <= r["probability"] <= r["ci_high"] <= 1


def test_evaluate_eligibility_tool(deps, settings):
    r = T.evaluate_eligibility_tool(deps, settings, "TEST-AR-003", "AR", "personal_loan", None, None)
    assert r["outcome"] == "No elegible" and r["explanation_pt"]


def test_create_handoff_valida_schema(deps):
    doc = {"case_id": "case-test", "customer_id": "TEST-MX-002", "locale": "es-MX", "reason_code": "regulatory", "request_summary": "x",
           "verified_facts": [], "actions_taken": [], "evidence": [], "open_questions": [], "risk_flags": [], "trace_id": "t"}
    assert T.create_handoff(deps, doc)["case_id"] == "case-test" and deps.store.get_handoff("case-test")


def test_run_tool_timeout_cold_una_vez(deps, settings):
    import time
    deps.health["sql"] = "cold"
    used = set()
    T.run_tool("get_customer_profile", lambda: time.sleep(0.01) or 1, deps, settings, cold_used=used)
    assert used == {"sql"}
    deps.health["sql"] = "ok"


def test_country_code_iso2_desde_perfil_o_fallback():
    from agent.tools import get_customer_profile, COUNTRY_ISO
    from agent.adapters import build_deps
    from agent.config.settings import Settings
    d = build_deps(Settings())
    assert get_customer_profile(d, "TEST-CO-001")["country_code"] == "CO"
    assert COUNTRY_ISO["México"] == "MX"
