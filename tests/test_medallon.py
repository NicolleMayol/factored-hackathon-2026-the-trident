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
