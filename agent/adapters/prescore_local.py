"""Pre-score en proceso: la regresión logística ganadora (ml/train_prescore.py, registrada en UC como hackathon.ml.prescore_lgbm)
exportada a policy/prescore_logreg.json. Misma matemática que el pyfunc, sin red: para el SKU trial, donde Model Serving no existe.
Contribuciones = coeficiente × valor estandarizado (las tres mayores en valor absoluto). AGENT_PRESCORE=local."""
from __future__ import annotations
import json
import math
from pathlib import Path
from typing import Any

from agent.config.settings import REPO_ROOT

NUMERIC = ["credit_score", "estimated_monthly_income", "n_tx", "amount_usd_12m", "declined_ratio", "active_months",
           "n_products", "n_active_products", "credit_limit_total", "balance_total", "n_cards", "n_loans"]


class PrescoreLocal:
    def __init__(self, settings=None):
        path = Path(getattr(settings, "prescore_local_path", "") or REPO_ROOT / "policy" / "prescore_logreg.json")
        self.m = json.loads(Path(path).read_text(encoding="utf-8"))
        self.model_version = self.m["version"]

    def _features(self, f: dict[str, Any]) -> dict[str, float]:
        x: dict[str, Any] = {}
        for k in NUMERIC:
            v = f.get(k)
            x[k] = None if v in (None, "") else float(v)
        lim = x.get("credit_limit_total") or None
        x["utilization"] = (x["balance_total"] / lim) if (lim and x.get("balance_total") is not None) else None
        x["income_to_limit"] = (x["estimated_monthly_income"] / lim) if (lim and x.get("estimated_monthly_income") is not None) else None
        x["credit_score_missing"] = 1.0 if x.get("credit_score") is None else 0.0
        x["income_missing"] = 1.0 if x.get("estimated_monthly_income") is None else 0.0
        return x

    def predict(self, f: dict[str, Any]) -> dict[str, Any]:
        x = self._features(f); z = self.m["intercept"]; contrib = []
        for col, mu, sd, w in zip(self.m["cols"], self.m["mean"], self.m["scale"], self.m["coef"]):
            v = x.get(col)
            if v is None or (isinstance(v, float) and math.isnan(v)):
                v = self.m["median"].get(col) or 0.0
            c = w * (v - mu) / (sd or 1.0)
            z += c; contrib.append((col, c))
        p = 1.0 / (1.0 + math.exp(-z))
        top = sorted(contrib, key=lambda t: -abs(t[1]))[:3]
        e = float(self.m.get("ece", 0.05))
        return {"probability": round(p, 3), "ci_low": round(max(0.0, p - e), 3), "ci_high": round(min(1.0, p + e), 3),
                "shap_top3": [[k, round(v, 3)] for k, v in top], "model_version": self.model_version}
