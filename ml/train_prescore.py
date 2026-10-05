"""Pre-score (ADR-06, ADR-21 §4c): LightGBM vs regresión logística sobre gold.customer_360 + gold.customer_behavior_12m, con MLflow y registro en UC.

    python ml/train_prescore.py --source mock              # dry run con data/mock (50 filas): valida el pipeline, no registra
    python ml/train_prescore.py --source gold              # lee gold por wh-agent (SQL_HTTP_PATH), registra hackathon.ml.prescore_lgbm
    python ml/train_prescore.py --source gold --no-register

Target (proxy, declarado): y = 1 si el cliente NO tuvo mora > 30 días en los últimos 12 meses (max_days_past_due <= 30). El pre-score es
"probabilidad de buen comportamiento", insumo del motor de reglas (E09/E10), nunca una decisión. Fuera de features: max_days_past_due
(es el target) y cualquier columna ref.* (regla Factored). Nulos sin imputar: NaN nativo en LightGBM + flags de ausencia (ADR-23).
Baseline: regresión logística con mediana (la logística no admite NaN; se declara). Métricas: AUC, Brier, ECE (10 bins), por país.
El modelo registrado es un pyfunc que devuelve el contrato de get_prescore: probability, ci_low, ci_high, shap_top3, model_version.
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:  # noqa: BLE001
    pass

NUM_V1 = ["credit_score", "estimated_monthly_income", "n_tx", "amount_usd_12m", "declined_ratio", "active_months"]
NUM_V2 = ["n_products", "n_active_products", "credit_limit_total", "balance_total", "utilization", "n_cards", "n_loans", "income_to_limit"]  # cartera (customer_products), sin days_past_due
CAT = ["segment", "country_code"]
FLAGS = ["credit_score_missing", "income_missing"]
NUM = NUM_V1 + NUM_V2
FEATURES = NUM + FLAGS + CAT
RAW_INPUTS = NUM_V1 + ["n_products", "n_active_products", "credit_limit_total", "balance_total", "n_cards", "n_loans"] + CAT  # lo que manda el agente; el resto se deriva
MODEL_NAME = "hackathon.ml.prescore_lgbm"
EXPERIMENT = os.environ.get("MLFLOW_EXPERIMENT", "/Shared/fh26/agente")


# ---------- datos ----------
def load_mock() -> pd.DataFrame:
    a = pd.read_csv(ROOT / "data" / "mock" / "customer_360.csv")
    b = pd.read_csv(ROOT / "data" / "mock" / "customer_behavior_12m.csv")
    pr = pd.read_csv(ROOT / "data" / "mock" / "customer_products.csv")
    agg = pr.groupby("customer_id").agg(n_products=("product_id", "count"), n_active_products=("product_status", lambda s: (s == "Active").sum()), credit_limit_total=("credit_limit", "sum"),
                                        balance_total=("current_balance", "sum"), n_cards=("product_type", lambda s: s.isin(["credit_card", "Tarjeta Crédito"]).sum()),
                                        n_loans=("product_type", lambda s: s.isin(["personal_loan", "mortgage", "payroll_loan", "Préstamo Personal", "Préstamo Hipotecario"]).sum())).reset_index()
    return derive(a.merge(b, on="customer_id", how="inner").merge(agg, on="customer_id", how="left"))


def load_gold() -> pd.DataFrame:
    """Lee las dos tablas por la Statement API (perfil local). Sin TEST-*: son filas sintéticas fuera de toda métrica (ADR-22)."""
    import requests
    from agent.adapters import dbx_auth
    host = dbx_auth.host(); wid = os.environ["SQL_HTTP_PATH"].rstrip("/").split("/")[-1]
    sql = ("WITH p AS (SELECT customer_id, COUNT(*) AS n_products, SUM(CASE WHEN product_status = 'Active' THEN 1 ELSE 0 END) AS n_active_products, "
           "SUM(COALESCE(credit_limit, 0)) AS credit_limit_total, SUM(COALESCE(current_balance, 0)) AS balance_total, "
           "SUM(CASE WHEN product_type IN ('Tarjeta Crédito', 'credit_card') THEN 1 ELSE 0 END) AS n_cards, "
           "SUM(CASE WHEN product_type IN ('Préstamo Personal', 'Préstamo Hipotecario', 'personal_loan', 'mortgage', 'payroll_loan') THEN 1 ELSE 0 END) AS n_loans "
           "FROM hackathon.gold.customer_products GROUP BY customer_id) "
           "SELECT c.customer_id, c.country_code, c.segment, c.credit_score, c.estimated_monthly_income, b.n_tx, b.amount_usd_12m, b.declined_ratio, "
           "b.max_days_past_due, b.active_months, p.n_products, p.n_active_products, p.credit_limit_total, p.balance_total, p.n_cards, p.n_loans "
           "FROM hackathon.gold.customer_360 c JOIN hackathon.gold.customer_behavior_12m b USING (customer_id) LEFT JOIN p USING (customer_id) "
           "WHERE c.customer_id NOT LIKE 'TEST-%'")
    r = requests.post(f"{host}/api/2.0/sql/statements", headers={**dbx_auth.auth_headers(), "Content-Type": "application/json"},
                      json={"warehouse_id": wid, "statement": sql, "wait_timeout": "50s", "on_wait_timeout": "CONTINUE", "format": "JSON_ARRAY", "disposition": "INLINE", "row_limit": 200000}, timeout=70)
    r.raise_for_status(); j = r.json(); sid = j["statement_id"]
    while j["status"]["state"] in ("PENDING", "RUNNING"):
        time.sleep(3); j = requests.get(f"{host}/api/2.0/sql/statements/{sid}", headers=dbx_auth.auth_headers(), timeout=30).json()
    if j["status"]["state"] != "SUCCEEDED":
        raise RuntimeError(j["status"])
    cols = [c["name"] for c in j["manifest"]["schema"]["columns"]]
    rows = list(j["result"].get("data_array", []))
    nxt = j["result"].get("next_chunk_internal_link")
    while nxt:  # paginación
        k = requests.get(f"{host}{nxt}", headers=dbx_auth.auth_headers(), timeout=60).json(); rows += k.get("data_array", []); nxt = k.get("next_chunk_internal_link")
    df = pd.DataFrame(rows, columns=cols)
    return derive(df)


def derive(df: pd.DataFrame) -> pd.DataFrame:
    """Features derivadas de cartera (v2). Con el mock (sin agregados) quedan en NaN: LightGBM las trata como ausentes."""
    for c in ["n_products", "n_active_products", "credit_limit_total", "balance_total", "n_cards", "n_loans"]:
        if c not in df.columns:
            df[c] = np.nan
    for c in NUM_V1 + ["max_days_past_due", "n_products", "n_active_products", "credit_limit_total", "balance_total", "n_cards", "n_loans"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df["utilization"] = df["balance_total"] / df["credit_limit_total"].replace(0, np.nan)
    df["income_to_limit"] = df["estimated_monthly_income"] / df["credit_limit_total"].replace(0, np.nan)
    return df


def prepare(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    df = df.copy()
    df["credit_score_missing"] = df["credit_score"].isna().astype(int)
    df["income_missing"] = df["estimated_monthly_income"].isna().astype(int)
    for c in CAT:
        df[c] = df[c].astype("category")
    y = (df["max_days_past_due"].fillna(0) <= 30).astype(int)
    return df[FEATURES], y


# ---------- métricas ----------
def ece(y: np.ndarray, p: np.ndarray, bins: int = 10) -> float:
    edges = np.linspace(0, 1, bins + 1); e = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (p >= lo) & (p < hi) if hi < 1 else (p >= lo) & (p <= hi)
        if m.any():
            e += m.mean() * abs(y[m].mean() - p[m].mean())
    return float(e)


def evaluate(y: np.ndarray, p: np.ndarray) -> dict:
    from sklearn.metrics import brier_score_loss, roc_auc_score
    auc = float(roc_auc_score(y, p)) if len(np.unique(y)) > 1 else float("nan")
    return {"auc": round(auc, 4), "brier": round(float(brier_score_loss(y, p)), 4), "ece": round(ece(y, p), 4), "n": int(len(y)), "positive_rate": round(float(y.mean()), 4)}


# ---------- pyfunc con el contrato de get_prescore ----------
class PrescoreModel:
    """Devuelve el contrato de contracts/tools.yaml · get_prescore. ci = p ± ECE del test (incertidumbre de calibración, declarada).
    kind = lgb (SHAP por pred_contrib) o logreg (contribución = coeficiente × valor estandarizado)."""
    def __init__(self, kind: str, cols: list[str], model=None, categories: dict | None = None, median=None, ece_width: float = 0.05, version: str = ""):
        self.kind, self.cols, self.model, self.categories, self.median, self.ece_width, self.version = kind, cols, model, categories or {}, median, ece_width, version

    @classmethod
    def from_lgb(cls, booster, cols, categories):
        return cls("lgb", cols, booster, categories)

    @classmethod
    def from_logreg(cls, pipe, median, cols):
        return cls("logreg", cols, pipe, None, median)

    def _frame(self, rows: list[dict]) -> pd.DataFrame:
        df = derive(pd.DataFrame(rows))
        for c in NUM:
            df[c] = pd.to_numeric(df.get(c), errors="coerce")
        df["credit_score_missing"] = df["credit_score"].isna().astype(int)
        df["income_missing"] = df["estimated_monthly_income"].isna().astype(int)
        for c in CAT:
            if c in self.cols:
                df[c] = pd.Categorical(df.get(c), categories=self.categories[c])
        return df[self.cols]

    def predict(self, rows: list[dict]) -> list[dict]:
        X = self._frame(rows)
        if self.kind == "lgb":
            p = self.model.predict(X); contrib = self.model.predict(X, pred_contrib=True)[:, :-1]
        else:
            Xf = X.fillna(self.median)
            p = self.model.predict_proba(Xf)[:, 1]
            z = self.model.named_steps["standardscaler"].transform(Xf)
            contrib = z * self.model.named_steps["logisticregression"].coef_[0]
        out = []
        for i, pi in enumerate(p):
            top = sorted(zip(self.cols, contrib[i]), key=lambda t: -abs(float(t[1])))[:3]
            out.append({"probability": round(float(pi), 3), "ci_low": round(max(0.0, float(pi) - self.ece_width), 3), "ci_high": round(min(1.0, float(pi) + self.ece_width), 3),
                        "shap_top3": [[k, round(float(v), 3)] for k, v in top], "model_version": self.version})
        return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--source", choices=["mock", "gold"], default="mock"); ap.add_argument("--no-register", action="store_true")
    a = ap.parse_args()
    import lightgbm as lgb
    import mlflow
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import train_test_split
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    df = load_mock() if a.source == "mock" else load_gold()
    X, y = prepare(df)
    strat = y if y.nunique() > 1 and y.value_counts().min() >= 2 else None
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=42, stratify=strat)
    version = f"prescore-lgbm-{time.strftime('%Y%m%d')}-{a.source}"

    # baseline: logística con mediana (declarado) sobre numéricas + flags; v1 = perfil + comportamiento, v2 = + cartera
    def fit_logreg(cols):
        med = Xtr[cols].median()
        pipe = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000)).fit(Xtr[cols].fillna(med), ytr)
        return (pipe, med), pipe.predict_proba(Xte[cols].fillna(med))[:, 1]
    L1 = NUM_V1 + FLAGS; L2 = NUM + FLAGS
    base_v1, p_b1 = fit_logreg(L1); m_b1 = evaluate(yte.values, p_b1)
    base, p_base = fit_logreg(L2); m_base = evaluate(yte.values, p_base)

    # LightGBM: NaN nativo, categóricas nativas. v1 = features de 360+behavior; v2 = + cartera (customer_products)
    params = {"objective": "binary", "learning_rate": 0.05, "num_leaves": 15, "min_data_in_leaf": max(5, len(Xtr) // 200), "feature_fraction": 0.9, "bagging_fraction": 0.9, "bagging_freq": 1, "verbose": -1, "seed": 42}
    def fit_lgb(cols):
        dtr = lgb.Dataset(Xtr[cols], ytr, categorical_feature=[c for c in CAT if c in cols]); dte = lgb.Dataset(Xte[cols], yte, reference=dtr)
        b = lgb.train(params, dtr, num_boost_round=400, valid_sets=[dte], callbacks=[lgb.early_stopping(30, verbose=False)])
        return b, b.predict(Xte[cols], num_iteration=b.best_iteration)
    V1 = NUM_V1 + FLAGS + CAT
    booster_v1, p_v1 = fit_lgb(V1); m_v1 = evaluate(yte.values, p_v1)
    booster, p_lgb = fit_lgb(FEATURES); m_lgb = evaluate(yte.values, p_lgb)
    experiments = {"logreg_v1": m_b1, "logreg_v2_cartera": m_base, "lightgbm_v1": m_v1, "lightgbm_v2_cartera": m_lgb}
    ORDER = ["logreg_v1", "logreg_v2_cartera", "lightgbm_v1", "lightgbm_v2_cartera"]  # de más simple a más complejo
    top = max(experiments[k]["auc"] for k in ORDER)
    best = next(k for k in ORDER if experiments[k]["auc"] >= top - 0.005)  # dentro de 0,005 del mejor AUC → gana el más simple
    print("experimentos:", json.dumps({k: v["auc"] for k, v in experiments.items()}), "→ ganador:", best)
    by_country = {c: evaluate(yte.values[Xte["country_code"].values == c], p_lgb[Xte["country_code"].values == c]) for c in sorted(Xte["country_code"].dropna().unique())}
    imp = dict(zip(FEATURES, booster.feature_importance("gain").round(1).tolist()))
    report = {"version": version, "source": a.source, "n_total": int(len(X)), "features": FEATURES, "target": "max_days_past_due <= 30 (proxy, 12 m)",
              "experiments": experiments, "winner": best, "rule": "AUC dentro de 0,005 del mejor → el modelo más simple", "by_country": by_country, "importance_gain": imp, "best_iteration": int(booster.best_iteration or 0)}
    (ROOT / "ml" / "results").mkdir(parents=True, exist_ok=True)
    (ROOT / "ml" / "results" / f"prescore-{a.source}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("version", "n_total", "experiments", "winner", "by_country")}, ensure_ascii=False, indent=1))

    # MLflow: experimento del equipo; registro en UC solo con gold
    if a.source == "mock" and a.no_register is False:
        a.no_register = True
    mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "databricks"))
    try:
        mlflow.set_experiment(EXPERIMENT)
    except Exception as e:  # noqa: BLE001  — sin workspace (CI) se registra en local
        print(f"MLflow {type(e).__name__}: tracking local"); mlflow.set_tracking_uri(f"sqlite:///{ROOT / 'ml' / 'mlflow.db'}"); mlflow.set_experiment("prescore")
    with mlflow.start_run(run_name=version) as run:
        mlflow.log_params({**params, "source": a.source, "n_train": len(Xtr), "n_test": len(Xte), "target": report["target"]})
        mlflow.log_metrics({f"lgb_{k}": v for k, v in m_lgb.items() if isinstance(v, (int, float)) and not np.isnan(v)})
        for name, m in experiments.items():
            mlflow.log_metrics({f"{name}_{k}": v for k, v in m.items() if isinstance(v, (int, float)) and not np.isnan(v)})
        mlflow.set_tags({"winner": best, "features_v2": ",".join(NUM_V2), "rule": report["rule"]})
        for c, m in by_country.items():
            if not np.isnan(m["auc"]):
                mlflow.log_metric(f"lgb_auc_{c}", m["auc"])
        mlflow.log_dict(report, "report.json")
        cats = {c: [str(v) for v in X[c].cat.categories] for c in CAT}
        if best == "logreg_v1":
            model, cols, metr = PrescoreModel.from_logreg(*base_v1, L1), L1, m_b1
        elif best == "logreg_v2_cartera":
            model, cols, metr = PrescoreModel.from_logreg(*base, L2), L2, m_base
        elif best == "lightgbm_v1":
            model, cols, metr = PrescoreModel.from_lgb(booster_v1, V1, cats), V1, m_v1
        else:
            model, cols, metr = PrescoreModel.from_lgb(booster, FEATURES, cats), FEATURES, m_lgb
        model.ece_width, model.version = metr["ece"], f"{version}-{best}"
        wrapper = _PyFunc(model)
        if model.kind == "logreg":  # sin Model Serving (SKU trial): el mismo modelo, exportado a JSON para evaluarlo en proceso (agent/adapters/prescore_local.py)
            sc, lr = model.model.named_steps["standardscaler"], model.model.named_steps["logisticregression"]
            export = {"version": model.version, "kind": "logreg", "cols": cols, "mean": sc.mean_.tolist(), "scale": sc.scale_.tolist(), "coef": lr.coef_[0].tolist(),
                      "intercept": float(lr.intercept_[0]), "median": {k: (None if pd.isna(v) else float(v)) for k, v in model.median.items()}, "ece": float(metr["ece"]),
                      "auc_test": float(metr["auc"]), "n_train": int(len(Xtr)), "source": a.source, "target": report["target"]}
            out = ROOT / "policy" / "prescore_logreg.json"
            if a.source == "gold":
                out.write_text(json.dumps(export, ensure_ascii=False, indent=1), encoding="utf-8"); print(f"exportado {out} (coeficientes del modelo ganador)")
            mlflow.log_dict(export, "prescore_logreg.json")
        example = pd.DataFrame([{k: (None if pd.isna(v) else (float(v) if k in NUM else str(v))) for k, v in Xte.iloc[0][RAW_INPUTS].to_dict().items()}])
        kw = {"registered_model_name": MODEL_NAME} if not a.no_register else {}
        if not a.no_register:
            mlflow.set_registry_uri("databricks-uc")
        mlflow.pyfunc.log_model(name="model", python_model=wrapper, input_example=example, pip_requirements=["lightgbm", "scikit-learn", "pandas", "numpy"], **kw)
        print(f"MLflow run {run.info.run_id} · registrado: {'sí → ' + MODEL_NAME if not a.no_register else 'no'}")


import mlflow.pyfunc as _pf  # noqa: E402


class _PyFunc(_pf.PythonModel):
    """Envoltorio mlflow.pyfunc: input = lista de dicts (dataframe_records); output = lista de dicts del contrato."""
    def __init__(self, inner=None):
        self.inner = inner

    def predict(self, context, model_input, params=None):
        rows = model_input.to_dict(orient="records") if hasattr(model_input, "to_dict") else list(model_input)
        return self.inner.predict(rows)


if __name__ == "__main__":
    main()
