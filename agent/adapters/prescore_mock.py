"""Pre-scoring mock: función monótona del credit_score y la mora, con intervalo. Devuelve banda, nunca decisión."""
from __future__ import annotations
from typing import Any


class PrescoreMock:
    model_version = "prescore-mock-0"

    def __init__(self, settings=None):
        pass

    def predict(self, f: dict[str, Any]) -> dict[str, Any]:
        score = float(f.get("credit_score") or 600)
        dpd = float(f.get("max_days_past_due") or 0)
        declined = float(f.get("declined_ratio") or 0)
        p = max(0.02, min(0.98, (score - 300) / 550 - 0.3 * min(dpd, 90) / 90 - 0.2 * declined))
        return {"probability": round(p, 3), "ci_low": round(max(0, p - 0.08), 3), "ci_high": round(min(1, p + 0.08), 3),
                "shap_top3": [["credit_score", round((score - 600) / 550, 3)], ["max_days_past_due", round(-dpd / 90, 3)], ["declined_ratio", round(-declined, 3)]],
                "model_version": self.model_version}
