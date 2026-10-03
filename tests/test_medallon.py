"""Tests del medallón (datos). No necesitan Spark ni workspace: validan el contrato, que es lo que
se desincroniza en silencio.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data" / "medallon" / "src"))
import schemas  # noqa: E402

LANDING = "abfss://landing@adlsagentbankdev.dfs.core.windows.net/factored-datathon/data"


def test_las_13_fuentes_del_diccionario():
    assert len(schemas.FUENTES) == 13
    assert len(schemas.RAIZ) == 6 and len(schemas.PARTICIONADAS) == 7
    assert set(schemas.FUENTES) == set(schemas.FILAS_DICCIONARIO)


def test_a_silver_son_7_y_estan_en_las_fuentes():
    assert len(schemas.A_SILVER) == 7
    assert set(schemas.A_SILVER) <= set(schemas.FUENTES)
    # Las tres grandes que ADR-22 deja en bronze: 12,08 M de filas que no alimentan gold.
    for fuera in ("digital_events", "campaign_sends", "complaints"):
        assert fuera not in schemas.A_SILVER


@pytest.mark.parametrize("fuente", schemas.FUENTES)
def test_multiline_y_csv_en_todas_las_fuentes(fuente):
    """ADR-23: sin multiLine, call_transcripts da 548.336 filas en vez de 171.321 y las columnas
    se corren. El pipeline no falla: entrega basura. Por eso es un test y no un comentario."""
    o = schemas.opciones(fuente)
    assert o["cloudFiles.format"] == "csv"
    assert o["multiLine"] == "true"
    assert o["header"] == "true"
    assert o["rescuedDataColumn"] == "_rescued_data"
    # Sin escape de comilla doble, el JSON de mentioned_entities corre las columnas siguientes y el
    # conteo de filas no cambia: la corrupción es invisible salvo que se mire el contenido.
    assert o["escape"] == '"'


def test_rutas_raiz_vs_particionadas():
    assert schemas.ruta(LANDING, "customers") == f"{LANDING}/customers.csv"
    assert schemas.ruta(LANDING, "transactions") == f"{LANDING}/transactions/"
    # La barra final importa: sin ella Auto Loader no recorre las particiones year=/month=/day=.
    for f in schemas.PARTICIONADAS:
        assert schemas.ruta(LANDING, f).endswith("/")


def test_hints_cubren_las_columnas_tipadas_del_contrato():
    """La inferencia da DOUBLE donde contracts/gold.yaml dice int o decimal (ADR-23)."""
    assert "credit_score INT" in schemas.HINTS["customers"]
    assert "days_past_due INT" in schemas.HINTS["products"]
    # duration_seconds entra como texto a propósito: hay valores no numéricos y silver los castea
    # contando el descarte, en vez de perder la fila entera en _rescued_data.
    assert "duration_seconds STRING" in schemas.HINTS["call_transcripts"]


# --------------------------------------------------------------------------- contrato con ia-ml
# Prometido en ADR-22: las cabeceras de data/mock/*.csv y contracts/gold.yaml se verifican en las
# dos direcciones. El mock es lo que lee el agente con AGENT_SQL=mock; la tabla es lo que lee con
# AGENT_SQL=real. Si divergen, cambiar de modo rompe el agente sin que nadie lo note.
MOCK_A_TABLA = {
    "customer_360": "gold.customer_360",
    "customer_products": "gold.customer_products",
    "customer_behavior_12m": "gold.customer_behavior_12m",
    "intent_labels": "gold.intent_labels",
    "contact_demand": "gold.contact_demand",
    "credit_product_catalog": "gold.credit_product_catalog",
    "regulator_rates": "ref.regulator_rates",
}

# Deriva conocida y con dueño: ia-ml fijó rate_kind en la review del PR #23
# (`string, values: [ea, tna, cat, cft, usura]`). Entra al contrato con E6 y esta excepción se borra.
DERIVA_ACEPTADA = {("regulator_rates", "rate_kind")}


@pytest.mark.parametrize("mock,tabla", sorted(MOCK_A_TABLA.items()))
def test_cabeceras_del_mock_coinciden_con_el_contrato(mock, tabla):
    contrato = yaml.safe_load((ROOT / "contracts" / "gold.yaml").read_text(encoding="utf-8"))
    csv_path = ROOT / "data" / "mock" / f"{mock}.csv"
    if not csv_path.exists():
        pytest.skip(f"{csv_path.name} todavía no existe")
    cabecera = next(csv.reader(csv_path.open(encoding="utf-8")))
    columnas = list(contrato["tables"][tabla]["columns"])
    sobran = [c for c in cabecera if c not in columnas and (mock, c) not in DERIVA_ACEPTADA]
    faltan = [c for c in columnas if c not in cabecera]
    assert not sobran, f"{mock}.csv tiene columnas que {tabla} no declara: {sobran}"
    assert not faltan, f"{tabla} declara columnas que {mock}.csv no trae: {faltan}"


def test_country_code_cubre_las_dos_convenciones():
    """PR #27, opción 2: customer_360 lleva country_code para no traducir entre la convención de
    nombre completo y la ISO-2 de catalog, regulator_rates y policy_chunks. Si falta el mapeo de un
    país, el agente no falla: busca con un valor que no existe y recibe cero filas."""
    contrato = yaml.safe_load((ROOT / "contracts" / "gold.yaml").read_text(encoding="utf-8"))
    cols = contrato["tables"]["gold.customer_360"]["columns"]
    assert set(schemas.CODIGO_PAIS) == set(cols["country"]["values"])
    assert set(schemas.CODIGO_PAIS.values()) == set(cols["country_code"]["values"])


def test_el_contrato_dice_csv_no_parquet():
    """Regresión de ADR-23: gold.yaml decía parquet y los 7.671 archivos son CSV."""
    contrato = yaml.safe_load((ROOT / "contracts" / "gold.yaml").read_text(encoding="utf-8"))
    landing = contrato["source"]["landing"]
    assert landing["format"] == "csv"
    assert landing["format_opts"]["multiLine"] is True


# --------------------------------------------------------------------------- E5 · catálogo
def test_catalogo_generado_coincide_con_el_contrato():
    cat = yaml.safe_load((ROOT / "policy" / "catalog.yaml").read_text(encoding="utf-8"))
    contrato = yaml.safe_load((ROOT / "contracts" / "gold.yaml").read_text(encoding="utf-8"))
    cols = set(contrato["tables"]["gold.credit_product_catalog"]["columns"])
    assert cat["version"] == "v1" and len(cat["products"]) == 18
    for p in cat["products"]:
        faltan = cols - set(p) - {"_ingested_at"}
        assert not faltan, f"{p['product_code']} no trae {faltan}"
        assert p["es_sintetico"] is True
        assert p["rate_min"] <= p["rate_max"] and p["amount_min"] <= p["amount_max"]


def test_product_type_dataset_usa_los_valores_reales_del_origen():
    """Es la llave de join con gold.customer_products. Si no casa, evaluate_eligibility devuelve
    cero sin error (mismo patrón que country_code)."""
    reales = {"Préstamo Personal", "Tarjeta Crédito", "Préstamo Hipotecario"}  # medido en landing, ADR-23
    cat = yaml.safe_load((ROOT / "policy" / "catalog.yaml").read_text(encoding="utf-8"))
    declarados = {p["product_type_dataset"] for p in cat["products"] if p["product_type_dataset"]}
    assert declarados <= reales, f"valores que no existen en el dataset: {declarados - reales}"
    assert declarados == reales, "los tres productos de crédito del dataset deben tener contraparte"


def test_el_catalogo_vive_en_policy_y_el_agente_lo_lee_de_ahi():
    assert (ROOT / "policy" / "catalog.yaml").exists()
    settings = (ROOT / "agent" / "config" / "settings.py").read_text(encoding="utf-8")
    assert '"policy" / "catalog.yaml"' in settings


# --------------------------------------------------------------------------- E6 · tasas
RATE_KINDS = {"ea", "tna", "cat", "cft", "usura"}


def test_snapshot_de_tasas_respeta_dominio_y_grano():
    snaps = sorted((ROOT / "data" / "ref").glob("regulator_rates_*.csv"))
    assert snaps, "falta el snapshot de E6"
    filas = list(csv.DictReader(snaps[-1].open(encoding="utf-8")))
    contrato = yaml.safe_load((ROOT / "contracts" / "gold.yaml").read_text(encoding="utf-8"))
    assert set(filas[0]) == set(contrato["tables"]["ref.regulator_rates"]["columns"])
    assert {f["rate_kind"] for f in filas} <= RATE_KINDS
    llaves = [(f["country"], f["product_type"], f["rate_kind"]) for f in filas]
    assert len(llaves) == len(set(llaves)), "grano roto: país × producto × rate_kind debe ser único"


def test_cada_pais_tiene_su_techo_legal():
    """CO usura, MX cat, AR cft (decisión de ia-ml en el PR #23). Sin techo, el motor no puede
    acotar una simulación y citaría una tasa sin límite legal."""
    snaps = sorted((ROOT / "data" / "ref").glob("regulator_rates_*.csv"))
    filas = list(csv.DictReader(snaps[-1].open(encoding="utf-8")))
    techo = {"CO": "usura", "MX": "cat", "AR": "cft"}
    for pais, kind in techo.items():
        assert any(f["country"] == pais and f["rate_kind"] == kind for f in filas), f"falta el techo de {pais}"


def test_el_catalogo_nunca_ofrece_por_encima_del_techo_del_pais():
    """Revisión de ia-ml en el PR #31: si rate_max supera el tope, E11 manda toda simulación del
    país a revisión humana. El techo sale del mismo snapshot que lee el motor."""
    cap_kind = {"CO": "usura", "MX": "cat", "AR": "cft"}
    snaps = sorted((ROOT / "data" / "ref").glob("regulator_rates_*.csv"))
    techos: dict[tuple[str, str], float] = {}
    for f in csv.DictReader(snaps[-1].open(encoding="utf-8")):
        if f["rate_kind"] == cap_kind.get(f["country"]) and f["rate_max"]:
            techos[(f["country"], f["product_type"])] = float(f["rate_max"])
    cat = yaml.safe_load((ROOT / "policy" / "catalog.yaml").read_text(encoding="utf-8"))
    for p in cat["products"]:
        techo = techos.get((p["country"], p["product_type"])) or techos.get((p["country"], "personal_loan"))
        if techo is not None:
            assert p["rate_max"] <= techo, f"{p['product_code']} ofrece {p['rate_max']} sobre el techo {techo}"
        # El recorte no puede invertir el rango: pasó al usar el techo más estricto del país.
        assert p["rate_min"] <= p["rate_max"], f"{p['product_code']}: rango invertido"


def test_amount_min_es_un_piso_de_producto_no_el_p10_de_saldos():
    """El p10 de credit_limit es la distribución de cupos ya otorgados; como mínimo dejaba CO-PL en
    75 M COP y mandaba cualquier préstamo pequeño a E07 (revisión de ia-ml, PR #31)."""
    cat = yaml.safe_load((ROOT / "policy" / "catalog.yaml").read_text(encoding="utf-8"))
    tope_consumo = {"COP": 1_000_000, "USD": 500, "ARS": 100_000}
    for p in cat["products"]:
        if p["product_type"] == "mortgage":
            continue
        assert p["amount_min"] <= tope_consumo[p["currency"]], \
            f"{p['product_code']}: amount_min {p['amount_min']} es demasiado alto para un piso"


def test_el_mock_de_tasas_sale_del_mismo_snapshot():
    """Petición de ia-ml en el PR #31: si se mantienen aparte, el techo del motor y el de la tabla
    real se separan sin que nadie lo note."""
    snaps = sorted((ROOT / "data" / "ref").glob("regulator_rates_*.csv"))
    snap = list(csv.DictReader(snaps[-1].open(encoding="utf-8")))
    mock = list(csv.DictReader((ROOT / "data" / "mock" / "regulator_rates.csv").open(encoding="utf-8")))
    assert snap == mock, "data/mock/regulator_rates.csv no coincide con el último snapshot"
