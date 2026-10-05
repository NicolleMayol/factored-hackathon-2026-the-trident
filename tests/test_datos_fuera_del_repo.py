"""ADR-28 F13 (ADR-12): ninguna fila del dataset de Factored llega al repo público.
Corre en pr-gate con el resto de pytest. Cuatro barreras, de la más simple a la más fina:
1. Solo los archivos de datos de la lista pueden estar versionados. Uno nuevo exige revisión de datos y agregarlo aquí.
2. Ningún archivo trae columnas que solo tiene el dataset real (documento, fecha de nacimiento).
3. Todo customer_id versionado es sintético: TEST-* (usuarios de prueba) o CCO/CMX/CAR-* (data/mock).
4. Ningún archivo de datos pasa de 500 filas: la tabla más chica del dataset (branches) tiene 350 y el resto, miles."""
from __future__ import annotations
import csv
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXT = {".csv", ".tsv", ".jsonl", ".parquet", ".xlsx", ".xls", ".avro", ".orc", ".delta"}
PERMITIDOS = {
    "data/mock/contact_demand.csv", "data/mock/credit_product_catalog.csv", "data/mock/customer_360.csv",
    "data/mock/customer_behavior_12m.csv", "data/mock/customer_products.csv", "data/mock/intent_labels.csv",
    "data/mock/policy_chunks.jsonl", "data/mock/regulator_rates.csv", "data/ref/regulator_rates_2026-10-02.csv",
    "eval/cases.jsonl", "eval/retrieval_cases.jsonl", "ml/data/intents_train.jsonl",
}
COLUMNAS_REALES = {"document_number", "date_of_birth"}
ID_SINTETICO = re.compile(r"^(TEST-[A-Z]{2}|CCO|CMX|CAR)-\d+$")
MAX_FILAS = 500


def _versionados() -> list[str]:
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split("\n")
    except (OSError, subprocess.CalledProcessError):  # sin git (zip): se revisa el árbol
        out = [str(p.relative_to(ROOT)) for p in ROOT.rglob("*") if p.is_file() and ".git" not in p.parts]
    return [f for f in out if Path(f).suffix.lower() in EXT]


def _filas(path: str) -> list[dict]:
    p = ROOT / path
    if p.suffix == ".jsonl":
        return [json.loads(line) for line in open(p, encoding="utf-8") if line.strip()]
    if p.suffix in (".csv", ".tsv"):
        return list(csv.DictReader(open(p, encoding="utf-8"), delimiter="\t" if p.suffix == ".tsv" else ","))
    return []


def test_solo_archivos_de_datos_permitidos():
    nuevos = sorted(set(_versionados()) - PERMITIDOS)
    assert not nuevos, f"Archivos de datos sin revisar: {nuevos}. Si son sintéticos, agrégalos a PERMITIDOS con revisión de datos (ADR-12)."


def test_sin_columnas_del_dataset_real():
    for f in _versionados():
        filas = _filas(f)
        cols = set().union(*(r.keys() for r in filas)) if filas else set()
        assert not cols & COLUMNAS_REALES, f"{f} trae {cols & COLUMNAS_REALES}: columna del dataset real"


def test_customer_id_versionados_son_sinteticos():
    for f in _versionados():
        reales = sorted({str(r["customer_id"]) for r in _filas(f) if r.get("customer_id") and not ID_SINTETICO.match(str(r["customer_id"]))})
        assert not reales, f"{f}: customer_id que no es sintético: {reales[:3]}"


def test_ningun_archivo_de_datos_es_un_volcado():
    for f in _versionados():
        assert len(_filas(f)) <= MAX_FILAS, f"{f} tiene más de {MAX_FILAS} filas: parece un volcado del dataset"


def test_el_guard_detecta_un_customer_id_real():
    assert ID_SINTETICO.match("TEST-CO-001") and ID_SINTETICO.match("CMX-0042")
    assert not ID_SINTETICO.match("123456789") and not ID_SINTETICO.match("CUST-000123")
