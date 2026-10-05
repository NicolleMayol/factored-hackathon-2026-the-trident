"""M5 · Etiqueta las frases plantilla de call_transcripts.customer_text → intent_label (contrato gold.intent_labels), de forma reproducible.

    python ml/label_phrases.py data/ref/customer_text_phrases.csv      # CSV de una columna (customer_text), sin PII, lo entrega datos
    → escribe docs/labels.csv (customer_text, intent_label, action_label, label_source, rule) y actualiza la tabla de docs/labels.md

Reglas: (1) override manual de docs/labels.md (tabla "Overrides") gana siempre; (2) si no, el clasificador baseline de ml/intent_classifier.py
con umbral de confianza 0,6; (3) si no alcanza el umbral, out_of_scope con rule = "low_confidence" para revisión. action_label sale de
policy/policy.yaml (intención → acción por defecto con scopes completos): product_info→answer, eligibility_simulation→confirm,
formal_application→escalate, disbursement→escalate, out_of_scope→clarify. label_source = manual | model | low_confidence."""
from __future__ import annotations
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ACTION = {"product_info": "answer", "eligibility_simulation": "confirm", "formal_application": "escalate", "disbursement": "escalate", "out_of_scope": "clarify"}


def overrides() -> dict[str, str]:
    """Lee la tabla de overrides de docs/labels.md: | frase | intent |."""
    out = {}
    md = ROOT / "docs" / "labels.md"
    if not md.exists():
        return out
    sec = md.read_text(encoding="utf-8").split("## Overrides")[-1]
    for line in sec.splitlines():
        m = re.match(r"\|\s*(.+?)\s*\|\s*(product_info|eligibility_simulation|formal_application|disbursement|out_of_scope)\s*\|", line)
        if m:
            out[m.group(1).strip()] = m.group(2)
    return out


def main(path: str):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from ml.intent_classifier import load_train
    phrases = [r[0].strip() for r in csv.reader(open(path, encoding="utf-8")) if r and r[0].strip() and r[0].strip().lower() != "customer_text"]
    Xtr, ytr, _ = load_train()
    clf = make_pipeline(TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True), LogisticRegression(max_iter=2000, C=5.0, class_weight="balanced")).fit(Xtr, ytr)
    ov = overrides(); rows = []
    for ph in phrases:
        if ph in ov:
            it, src, rule = ov[ph], "manual", "override"
        else:
            proba = clf.predict_proba([ph])[0]; k = int(proba.argmax()); conf = float(proba[k]); it = clf.classes_[k]
            src, rule = ("model", f"p={conf:.2f}") if conf >= 0.6 else ("low_confidence", f"p={conf:.2f}")
            if src == "low_confidence":
                it = "out_of_scope"
        rows.append({"customer_text": ph, "intent_label": it, "action_label": ACTION[it], "label_source": src, "rule": rule})
    out = ROOT / "docs" / "labels.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    md = ROOT / "docs" / "labels.md"; s = md.read_text(encoding="utf-8")
    table = "| # | customer_text | intent_label | action_label | fuente |\n| --- | --- | --- | --- | --- |\n" + "\n".join(f"| {i+1} | {r['customer_text']} | `{r['intent_label']}` | `{r['action_label']}` | {r['label_source']} ({r['rule']}) |" for i, r in enumerate(rows))
    s = re.sub(r"<!-- tabla:inicio -->.*?<!-- tabla:fin -->", f"<!-- tabla:inicio -->\n{table}\n<!-- tabla:fin -->", s, flags=re.S)
    md.write_text(s, encoding="utf-8")
    from collections import Counter
    print(f"{len(rows)} frases → docs/labels.csv · {dict(Counter(r['intent_label'] for r in rows))} · fuentes {dict(Counter(r['label_source'] for r in rows))}")


if __name__ == "__main__":
    main(sys.argv[1])
