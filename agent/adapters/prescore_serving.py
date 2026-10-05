"""Pre-score real: endpoint de Model Serving PRESCORE_ENDPOINT (modelo hackathon.ml.prescore_lgbm, ml/train_prescore.py).
El pyfunc devuelve el contrato de get_prescore (probability, ci_low, ci_high, shap_top3, model_version); aquí solo se transporta.
Misma interfaz que PrescoreMock. Timeout de tool (8 s); frío: el endpoint escala a cero y tarda ~30 s la primera vez (run_tool lo tolera)."""
from __future__ import annotations
from typing import Any
import requests
from agent.adapters import dbx_auth

FEATURES = ["credit_score", "estimated_monthly_income", "n_tx", "amount_usd_12m", "declined_ratio", "active_months", "segment", "country_code",
            "n_products", "n_active_products", "credit_limit_total", "balance_total", "n_cards", "n_loans"]  # v2: agregados de cartera (get_prescore los calcula)


class PrescoreServing:
    def __init__(self, settings):
        self.s = settings
        self.host = (settings.databricks_host or dbx_auth.host()).rstrip("/")
        self.endpoint = settings.prescore_endpoint
        self.model_version = f"serving:{self.endpoint}"

    def predict(self, f: dict[str, Any]) -> dict[str, Any]:
        row = {k: f.get(k) for k in FEATURES}
        for k in FEATURES:
            if k in ("segment", "country_code"):
                continue
            row[k] = None if row[k] in (None, "") else float(row[k])
        r = requests.post(f"{self.host}/serving-endpoints/{self.endpoint}/invocations", timeout=self.s.tool_timeout_cold_s,
                          headers={**dbx_auth.auth_headers(), "Content-Type": "application/json"}, json={"dataframe_records": [row]})
        r.raise_for_status()
        pred = r.json().get("predictions", [])
        out = pred[0] if pred else {}
        if "probability" not in out:
            raise RuntimeError(f"prescore_serving: respuesta sin probability: {str(r.text)[:120]}")
        self.model_version = out.get("model_version", self.model_version)
        return {"probability": float(out["probability"]), "ci_low": float(out["ci_low"]), "ci_high": float(out["ci_high"]),
                "shap_top3": [[str(k), float(v)] for k, v in out.get("shap_top3", [])], "model_version": self.model_version}
