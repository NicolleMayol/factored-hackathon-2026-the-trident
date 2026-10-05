"""sql_warehouse sin red: la API de SQL Statements se simula. Verifica la consulta, los parámetros,
el tipado igual al mock y que catálogo y tasas sigan saliendo de los CSV."""
from types import SimpleNamespace

import pytest

from agent.adapters import sql_warehouse as W


class Resp:
    def __init__(self, j):
        self._j = j

    def raise_for_status(self):
        pass

    def json(self):
        return self._j


@pytest.fixture
def wh(monkeypatch, tmp_path):
    monkeypatch.setattr(W.dbx_auth, "host", lambda: "https://adb.example")
    monkeypatch.setattr(W.dbx_auth, "auth_headers", lambda: {"Authorization": "Bearer x"})
    from agent.config.settings import get_settings
    s = get_settings()
    return W.SQLWarehouse(SimpleNamespace(sql_http_path="/sql/1.0/warehouses/abc123", mock_dir=s.mock_dir))


def test_perfil_desde_gold(wh, monkeypatch):
    sent = {}

    def post(url, json, headers, timeout):
        sent.update(url=url, body=json)
        return Resp({"statement_id": "s1", "status": {"state": "SUCCEEDED"},
                     "manifest": {"schema": {"columns": [{"name": "customer_id"}, {"name": "credit_score"}, {"name": "estimated_monthly_income"}]}},
                     "result": {"data_array": [["TEST-CO-001", "780", None]]}})

    monkeypatch.setattr(W.requests, "post", post)
    rows = wh.query("customer_profile", {"customer_id": "TEST-CO-001"})
    assert sent["url"] == "https://adb.example/api/2.0/sql/statements"
    assert sent["body"]["warehouse_id"] == "abc123"
    assert sent["body"]["statement"] == "SELECT * FROM hackathon.gold.customer_360 WHERE customer_id = :v"
    assert sent["body"]["parameters"] == [{"name": "v", "value": "TEST-CO-001"}]
    assert rows == [{"customer_id": "TEST-CO-001", "credit_score": 780, "estimated_monthly_income": None}]


def test_espera_si_el_warehouse_esta_frio(wh, monkeypatch):
    monkeypatch.setattr(W.requests, "post", lambda *a, **k: Resp({"statement_id": "s1", "status": {"state": "PENDING"}}))
    monkeypatch.setattr(W.time, "sleep", lambda s: None)
    done = {"statement_id": "s1", "status": {"state": "SUCCEEDED"},
            "manifest": {"schema": {"columns": [{"name": "customer_id"}]}}, "result": {"data_array": [["TEST-MX-002"]]}}
    monkeypatch.setattr(W.requests, "get", lambda *a, **k: Resp(done))
    assert wh.query("customer_products", {"customer_id": "TEST-MX-002"}) == [{"customer_id": "TEST-MX-002"}]


def test_error_de_sql_no_pasa_en_silencio(wh, monkeypatch):
    monkeypatch.setattr(W.requests, "post", lambda *a, **k: Resp({"statement_id": "s1", "status": {"state": "FAILED", "error": {"message": "TABLE_OR_VIEW_NOT_FOUND"}}}))
    with pytest.raises(RuntimeError, match="TABLE_OR_VIEW_NOT_FOUND"):
        wh.query("customer_behavior", {"customer_id": "TEST-CO-001"})


def test_catalogo_y_tasas_desde_csv(wh, monkeypatch):
    monkeypatch.setattr(W.requests, "post", lambda *a, **k: pytest.fail("no debe ir al warehouse"))
    assert wh.query("regulator_rates", {"country": "AR", "product_type": "personal_loan"})
    assert wh.query("product_catalog", {"country": "CO"})
