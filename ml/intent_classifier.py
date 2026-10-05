"""Clasificador de intención (ADR-07, ADR-21 §4c): baseline TF-IDF (n-gramas de caracteres, es+pt) + regresión logística.

    python ml/intent_classifier.py                       # entrena con ml/data/intents_train.jsonl, evalúa en eval/cases.jsonl, escribe ml/results/intent.json
    python ml/intent_classifier.py --llm eval/results/v2-70b.json   # además, macro-F1 del LLM a partir de un run de run_eval (columna intent)

Por qué así: gold.intent_labels no es entrenable (42 frases plantilla bajo las 6 categorías, PR #31 · ADR-07), así que el entrenamiento
usa un set sintético propio del workflow 4 (109 frases es/pt, ml/data/intents_train.jsonl, escrito a mano) y el held-out son los
mensajes únicos de eval/cases.jsonl (dev set del agente, etiquetados con `intent`). Ningún texto se repite entre los dos. Macro-F1 por
idioma, matriz de confusión y los errores, en ml/results/intent.json. El clasificador NO va en el agente: Understand usa el LLM; esto
es el baseline que la rúbrica pide y la vara contra la que se mide el LLM (ADR-06)."""
from __future__ import annotations
import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
INTENTS = ["product_info", "eligibility_simulation", "formal_application", "disbursement", "out_of_scope"]


def load_train():
    rows = [json.loads(l) for l in open(ROOT / "ml" / "data" / "intents_train.jsonl", encoding="utf-8") if l.strip()]
    return [r["text"] for r in rows], [r["intent"] for r in rows], [r["language"] for r in rows]


def load_heldout():
    from agent.cli import USERS
    from agent.config.settings import Settings
    from eval.amounts import resolve_amounts
    s = Settings(); seen = set(); X, y, lang = [], [], []
    for l in open(ROOT / "eval" / "cases.jsonl", encoding="utf-8"):
        c = json.loads(l); msg = resolve_amounts(c["message"], USERS[c["user"]], s)
        if msg in seen or not c.get("intent"):
            continue
        seen.add(msg); X.append(msg); y.append(c["intent"]); lang.append(c["language"])
    return X, y, lang


def macro_f1(y, p, labels=INTENTS) -> float:
    from sklearn.metrics import f1_score
    return round(float(f1_score(y, p, labels=[x for x in labels if x in set(y) | set(p)], average="macro", zero_division=0)), 3)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--llm", help="results json de run_eval con intent/intent_expected por fila")
    a = ap.parse_args()
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import confusion_matrix
    from sklearn.pipeline import make_pipeline

    Xtr, ytr, ltr = load_train(); Xte, yte, lte = load_heldout()
    assert not set(Xtr) & set(Xte), "un texto de entrenamiento está en el held-out"
    clf = make_pipeline(TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=1, sublinear_tf=True), LogisticRegression(max_iter=2000, C=5.0, class_weight="balanced"))
    clf.fit(Xtr, ytr)
    pred = clf.predict(Xte)
    res = {"model": "tfidf_char2-5+logreg", "n_train": len(Xtr), "n_heldout": len(Xte),
           "macro_f1": {"all": macro_f1(yte, pred), **{lg: macro_f1([y for y, l in zip(yte, lte) if l == lg], [p for p, l in zip(pred, lte) if l == lg]) for lg in ("es", "pt")}},
           "confusion": {"labels": INTENTS, "matrix": confusion_matrix(yte, pred, labels=INTENTS).tolist()},
           "errors": [{"text": x, "expected": y, "predicted": p} for x, y, p in zip(Xte, yte, pred) if y != p]}
    if a.llm and Path(a.llm).exists():
        rows = json.load(open(a.llm, encoding="utf-8"))["rows"]
        rows = [r for r in rows if r.get("intent_expected") and r.get("intent")]
        if rows:
            res["llm"] = {"source": a.llm, "n": len(rows), "macro_f1": {"all": macro_f1([r["intent_expected"] for r in rows], [r["intent"] for r in rows]),
                          **{lg: macro_f1([r["intent_expected"] for r in rows if r["language"] == lg], [r["intent"] for r in rows if r["language"] == lg]) for lg in ("es", "pt")}}}
    (ROOT / "ml" / "results").mkdir(parents=True, exist_ok=True)
    (ROOT / "ml" / "results" / "intent.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("model", "n_train", "n_heldout", "macro_f1")}, ensure_ascii=False))
    for e in res["errors"]:
        print(f"  {e['expected']:>22} → {e['predicted']:<22} | {e['text'][:60]}")
    if "llm" in res:
        print("LLM:", json.dumps(res["llm"]["macro_f1"]))
    try:  # MLflow opcional: experimento del equipo
        import mlflow
        mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "databricks")); mlflow.set_experiment(os.environ.get("MLFLOW_EXPERIMENT", "/Shared/fh26/agente"))
        with mlflow.start_run(run_name="intent-tfidf-logreg"):
            mlflow.log_params({"model": res["model"], "n_train": len(Xtr), "n_heldout": len(Xte)})
            mlflow.log_metrics({f"macro_f1_{k}": v for k, v in res["macro_f1"].items()})
            if "llm" in res:
                mlflow.log_metrics({f"llm_macro_f1_{k}": v for k, v in res["llm"]["macro_f1"].items()})
            mlflow.log_dict(res, "intent.json")
        print("MLflow: run registrado en", os.environ.get("MLFLOW_EXPERIMENT", "/Shared/fh26/agente"))
    except Exception as e:  # noqa: BLE001
        print(f"MLflow omitido ({type(e).__name__})")


if __name__ == "__main__":
    main()
