"""Guard de fuentes externas (ADR-21, regla acordada con Factored): nada externo entra a entrenamiento ni a evaluación.
Corre con pytest (CI) y también directo: python eval/test_external_guard.py"""
from __future__ import annotations
import csv
import json
import sys
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_ref_no_es_feature():
    gold = yaml.safe_load(open(ROOT / "contracts" / "gold.yaml", encoding="utf-8"))
    feats = gold.get("features", {}) or {}
    txt = json.dumps(feats)
    assert "ref." not in txt and "regulator" not in txt, "ref.* no puede ser feature del pre-scoring"
    excluded = gold["tables"]["gold.customer_360"]["excluded_from_features"]
    assert {"gender", "marital_status", "date_of_birth"} <= set(excluded)


def test_casos_de_eval_no_citan_fuentes_externas():
    for name in ("cases.jsonl", "retrieval_cases.jsonl"):
        for line in open(ROOT / "eval" / name, encoding="utf-8"):
            c = json.loads(line)
            assert c.get("source", "") in ("", "synthetic") and "http" not in json.dumps(c), c.get("case_id")


def test_tasas_externas_solo_como_referencia():
    """Las tasas de reguladores viven en ref.*: se usan en Verify y en el techo del motor, nunca como label."""
    rows = list(csv.DictReader(open(ROOT / "data" / "mock" / "regulator_rates.csv", encoding="utf-8")))
    assert all(r["source"] for r in rows)
    labels = list(csv.DictReader(open(ROOT / "data" / "mock" / "intent_labels.csv", encoding="utf-8")))
    assert not any(k.startswith("rate_") or k in ("source", "url") for k in labels[0])


if __name__ == "__main__":
    for fn in (test_ref_no_es_feature, test_casos_de_eval_no_citan_fuentes_externas, test_tasas_externas_solo_como_referencia):
        fn(); print("ok", fn.__name__)
    sys.exit(0)
