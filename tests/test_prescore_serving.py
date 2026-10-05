import agent.adapters.prescore_serving as ps
from agent.config.settings import Settings


def test_prescore_serving_transporta_el_contrato(monkeypatch):
    monkeypatch.setenv("DATABRICKS_HOST", "https://x"); sent = {}
    class R:
        status_code = 200; text = "{}"
        def raise_for_status(self): pass
        def json(self): return {"predictions": [{"probability": 0.81, "ci_low": 0.76, "ci_high": 0.86, "shap_top3": [["credit_score", 0.3]], "model_version": "prescore-lgbm-20261005-gold"}]}
    def fake_post(url, **kw):
        sent.update(kw["json"]); sent["url"] = url; return R()
    monkeypatch.setattr(ps.requests, "post", fake_post); monkeypatch.setattr(ps.dbx_auth, "auth_headers", lambda: {})
    out = ps.PrescoreServing(Settings()).predict({"credit_score": "780", "estimated_monthly_income": None, "segment": "Plus", "country_code": "CO", "n_tx": 10, "max_days_past_due": 0})
    assert sent["url"].endswith("/serving-endpoints/prescore-lgbm/invocations") and sent["dataframe_records"][0]["credit_score"] == 780.0 and sent["dataframe_records"][0]["estimated_monthly_income"] is None
    assert "max_days_past_due" not in sent["dataframe_records"][0] and out["probability"] == 0.81 and out["model_version"].startswith("prescore-lgbm")
