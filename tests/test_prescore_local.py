"""El pre-score en proceso reproduce la logística exportada (misma matemática que el pyfunc registrado)."""
import json
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from agent.adapters.prescore_local import PrescoreLocal


def test_local_igual_que_sklearn(tmp_path):
    rng = np.random.default_rng(0)
    cols = ["credit_score", "estimated_monthly_income", "n_tx", "utilization", "credit_score_missing", "income_missing"]
    X = rng.normal(size=(200, len(cols))); X[:, 0] = 600 + 100 * X[:, 0]; X[:, 1] = 3e6 + 1e6 * X[:, 1]; X[:, 4:] = 0
    y = (X[:, 0] + rng.normal(size=200) * 50 > 600).astype(int)
    pipe = make_pipeline(StandardScaler(), LogisticRegression(max_iter=500)).fit(X, y)
    sc, lr = pipe.named_steps["standardscaler"], pipe.named_steps["logisticregression"]
    export = {"version": "t", "kind": "logreg", "cols": cols, "mean": sc.mean_.tolist(), "scale": sc.scale_.tolist(), "coef": lr.coef_[0].tolist(),
              "intercept": float(lr.intercept_[0]), "median": {c: float(np.median(X[:, i])) for i, c in enumerate(cols)}, "ece": 0.02}
    f = tmp_path / "m.json"; f.write_text(json.dumps(export))
    class S: prescore_local_path = str(f)
    m = PrescoreLocal(S())
    row = {"credit_score": 700, "estimated_monthly_income": 4e6, "n_tx": 0.3, "credit_limit_total": 1000, "balance_total": 500}
    out = m.predict(row)
    x = np.array([[700, 4e6, 0.3, 0.5, 0, 0]])
    assert abs(out["probability"] - pipe.predict_proba(x)[0, 1]) < 1e-3 and out["ci_high"] - out["ci_low"] <= 0.041 and len(out["shap_top3"]) == 3


def test_nulos_usan_mediana_y_flags(tmp_path):
    export = {"version": "t", "kind": "logreg", "cols": ["credit_score", "credit_score_missing"], "mean": [600, 0], "scale": [100, 1], "coef": [1.0, -0.5], "intercept": 0.0, "median": {"credit_score": 650}, "ece": 0.0}
    f = tmp_path / "m.json"; f.write_text(json.dumps(export))
    class S: prescore_local_path = str(f)
    out = PrescoreLocal(S()).predict({"credit_score": None})
    import math
    assert abs(out["probability"] - 1 / (1 + math.exp(-(0.5 - 0.5)))) < 1e-6
