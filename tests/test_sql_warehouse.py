"""SQL real y trazas reales sin red: la Statement API se simula; se verifica forma de la consulta, parámetros, tipado y que la traza nunca rompa."""
import json
import pytest
from agent.config.settings import Settings
import agent.adapters.sql_warehouse as sw
import agent.adapters.trace_mlflow as tr


class R:
    def __init__(self, body, code=200):
        self._b, self.status_code = body, code
    def json(self): return self._b
    def raise_for_status(self):
        if self.status_code >= 400: raise RuntimeError(self.status_code)


def _settings(monkeypatch):
    monkeypatch.setenv("SQL_HTTP_PATH", "/sql/1.0/warehouses/abc123"); monkeypatch.setenv("DATABRICKS_HOST", "https://x")
    return Settings()


def test_query_parametrizada_y_tipada(monkeypatch):
    s = _settings(monkeypatch); calls = []
    def fake_post(url, **kw):
        calls.append(kw["json"])
        return R({"status": {"state": "SUCCEEDED"}, "manifest": {"schema": {"columns": [{"name": "customer_id", "type_name": "STRING"}, {"name": "credit_score", "type_name": "INT"}, {"name": "estimated_monthly_income", "type_name": "DECIMAL"}]}},
                  "result": {"data_array": [["TEST-CO-001", "780", "9500000.00"], ["TEST-CO-002", None, "1.5"]]}})
    monkeypatch.setattr(sw.requests, "post", fake_post); monkeypatch.setattr(sw.dbx_auth, "auth_headers", lambda: {"Authorization": "Bearer t"})
    rows = sw.SQLWarehouse(s).query("customer_profile", {"customer_id": "TEST-CO-001"})
    assert calls[0]["warehouse_id"] == "abc123" and ":customer_id" in calls[0]["statement"] and "TEST-CO-001" not in calls[0]["statement"]
    assert calls[0]["parameters"] == [{"name": "customer_id", "value": "TEST-CO-001", "type": "STRING"}]
    assert rows[0] == {"customer_id": "TEST-CO-001", "credit_score": 780, "estimated_monthly_income": 9500000.0} and rows[1]["credit_score"] is None


def test_tasas_cacheadas_y_filtro_por_producto(monkeypatch):
    s = _settings(monkeypatch); n = {"posts": 0}
    def fake_post(url, **kw):
        n["posts"] += 1
        return R({"status": {"state": "SUCCEEDED"}, "manifest": {"schema": {"columns": [{"name": "country", "type_name": "STRING"}, {"name": "product_type", "type_name": "STRING"}, {"name": "rate_kind", "type_name": "STRING"}, {"name": "rate_max", "type_name": "DECIMAL"}]}},
                  "result": {"data_array": [["CO", "personal_loan", "usura", "25.5"], ["CO", "credit_card", "usura", "25.5"]]}})
    monkeypatch.setattr(sw.requests, "post", fake_post); monkeypatch.setattr(sw.dbx_auth, "auth_headers", lambda: {})
    q = sw.SQLWarehouse(s)
    a = q.query("regulator_rates", {"country": "CO", "product_type": "credit_card"}); b = q.query("regulator_rates", {"country": "CO", "product_type": "personal_loan"})
    assert n["posts"] == 1 and len(a) == 1 and a[0]["product_type"] == "credit_card" and b[0]["rate_max"] == 25.5


def test_sin_path_falla_claro(monkeypatch):
    monkeypatch.delenv("SQL_HTTP_PATH", raising=False); monkeypatch.setenv("DATABRICKS_HOST", "https://x")
    with pytest.raises(RuntimeError, match="SQL_HTTP_PATH"):
        sw.SQLWarehouse(Settings())


def test_traza_inserta_con_arrays_y_no_rompe(monkeypatch):
    s = _settings(monkeypatch); stmts = []
    def fake_post(url, **kw):
        stmts.append(kw["json"]); return R({"status": {"state": "SUCCEEDED"}})
    monkeypatch.setattr(tr.requests, "post", fake_post); monkeypatch.setattr(tr.dbx_auth, "auth_headers", lambda: {})
    t = tr.TraceMlflow(s)
    t.log_turn({"trace_id": "abc", "conversation_id": "c1", "locale": "es-CO", "node_path": ["understand", "decide"], "tools_called": [], "rules_fired": ["P01"],
                "expected_action": None, "action": "answer", "escalate_reason": "none", "guardrail_hits": [], "groundedness": 1.0, "tokens_in": 120, "tokens_out": 40,
                "cost_usd": 0.0003, "latency_ms": 1234.5, "prompt_version": "v2", "model_version": "llama", "reply_source": "llm"})
    t.flush()
    assert stmts[0]["statement"].startswith("CREATE TABLE IF NOT EXISTS hackathon.ops.agent_turns")
    ins = stmts[1]
    assert ins["statement"].startswith("INSERT INTO hackathon.ops.agent_turns") and "from_json(:node_path, 'array<string>')" in ins["statement"]
    p = {x["name"]: x for x in ins["parameters"]}
    assert json.loads(p["node_path"]["value"]) == ["understand", "decide"] and p["tokens_in"]["type"] == "INT" and p["cost_usd"]["type"] == "DOUBLE" and "expected_action" not in p
    assert t.errors == 0


def test_traza_con_error_no_rompe_el_turno(monkeypatch):
    s = _settings(monkeypatch)
    monkeypatch.setattr(tr.requests, "post", lambda url, **kw: R({}, 500)); monkeypatch.setattr(tr.dbx_auth, "auth_headers", lambda: {})
    t = tr.TraceMlflow(s); t.log_turn({"trace_id": "x"}); t.flush()
    assert t.errors == 1


def test_cliente_memorizado_30s_y_sin_memo_con_0(monkeypatch):
    """Un turno de pre-evaluación pide customer_profile hasta 4 veces: con el memo de 30 s va un solo viaje; con 0 s, uno por llamada."""
    n = {"posts": 0}
    def fake_post(url, **kw):
        n["posts"] += 1
        return R({"status": {"state": "SUCCEEDED"}, "manifest": {"schema": {"columns": [{"name": "customer_id", "type_name": "STRING"}]}}, "result": {"data_array": [["TEST-CO-001"]]}})
    monkeypatch.setattr(sw.requests, "post", fake_post); monkeypatch.setattr(sw.dbx_auth, "auth_headers", lambda: {})
    q = sw.SQLWarehouse(_settings(monkeypatch))
    for _ in range(4):
        q.query("customer_profile", {"customer_id": "TEST-CO-001"})
    q.query("customer_profile", {"customer_id": "TEST-CO-002"})
    assert n["posts"] == 2  # un viaje por cliente
    monkeypatch.setenv("SQL_CUSTOMER_CACHE_S", "0"); q0 = sw.SQLWarehouse(Settings()); n["posts"] = 0; print("TTL", q0.s.sql_customer_cache_s, q0._cache)
    q0.query("customer_profile", {"customer_id": "TEST-CO-001"}); q0.query("customer_profile", {"customer_id": "TEST-CO-001"})
    assert n["posts"] == 2
