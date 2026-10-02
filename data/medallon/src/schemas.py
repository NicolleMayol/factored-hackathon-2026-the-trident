"""Catálogo de fuentes del medallón y hints de tipo (ADR-22, ADR-23).

Un solo sitio describe qué hay en `landing`, cómo se lee y con qué tipos. Lo usan el pipeline
(`bronze.py`) y los tests, para que el contrato no viva en dos sitios que se desincronizan.

Medido contra `landing` el 2026-10-02 (ADR-23):
  - los 7.671 archivos son CSV; no hay un solo Parquet
  - 6 CSV sueltos en la raíz (5 dimensiones + daily_exchange_rates) y 7 carpetas year=/month=/day=
  - `multiLine` es obligatorio: sin él call_transcripts da 548.336 filas en vez de 171.321
  - la inferencia no da los tipos del contrato, así que los que importan van como hint explícito
"""
from __future__ import annotations

# Las 6 fuentes que viven como un archivo suelto en la raíz de `landing`.
RAIZ = ("customers", "products", "branches", "service_agents", "marketing_campaigns", "daily_exchange_rates")

# Las 7 fuentes particionadas estilo Hive: <tabla>/year=YYYY/month=MM/day=DD/*.csv
PARTICIONADAS = (
    "transactions",
    "call_center_interactions",
    "call_transcripts",
    "satisfaction_surveys",
    "digital_events",
    "complaints",
    "campaign_sends",
)

FUENTES = RAIZ + PARTICIONADAS

# Las 7 que siguen a silver (ADR-22). Las otras 6 se quedan en bronze.
A_SILVER = (
    "customers",
    "products",
    "transactions",
    "call_center_interactions",
    "call_transcripts",
    "satisfaction_surveys",
    "daily_exchange_rates",
)

# Hints solo donde la inferencia no da el tipo del contrato (ADR-23). El resto lo infiere Auto Loader:
# forzar 40 columnas de texto no aporta nada y se desincroniza con el diccionario a la primera.
HINTS = {
    "customers": "credit_score INT, estimated_monthly_income DECIMAL(12,2)",
    "products": "days_past_due INT, current_balance DECIMAL(15,2), credit_limit DECIMAL(15,2), interest_rate DECIMAL(5,2)",
    "transactions": "amount DECIMAL(15,2), amount_usd DECIMAL(15,2), response_code STRING, fraud_score DECIMAL(5,2)",
    "call_center_interactions": "duration_seconds INT, wait_time_seconds INT, sentiment_score DECIMAL(3,2)",
    # duration_seconds se infiere STRING: hay valores no numéricos. Entra como texto y silver lo castea
    # contando el descarte, en vez de que Auto Loader mande la fila entera a _rescued_data.
    "call_transcripts": "duration_seconds STRING, accent_confidence DECIMAL(3,2)",
    "satisfaction_surveys": "main_score INT, question_1_response INT, question_2_response INT, question_3_response INT",
    "daily_exchange_rates": "exchange_rate DECIMAL(12,6), buy_rate DECIMAL(12,6), sell_rate DECIMAL(12,6)",
}

# Llave de negocio por fuente: la usa la dedup de silver y el check de grano de DQ.
LLAVES = {
    "customers": ["customer_id"],
    "products": ["product_id"],
    "transactions": ["transaction_id"],
    "call_center_interactions": ["interaction_id"],
    "call_transcripts": ["transcript_id"],
    "satisfaction_surveys": ["survey_id"],
    "daily_exchange_rates": ["date", "source_currency", "target_currency"],
}

# Filas que declara el diccionario de Factored v1.0.0. Son nominales: call_transcripts trae 171.321
# reales (ADR-23). Sirven de orden de magnitud en DQ, no de umbral exacto.
FILAS_DICCIONARIO = {
    "customers": 150_000,
    "products": 400_000,
    "branches": 350,
    "service_agents": 1_200,
    "marketing_campaigns": 200,
    "daily_exchange_rates": 3_000,
    "transactions": 5_000_000,
    "call_center_interactions": 800_000,
    "call_transcripts": 200_000,
    "satisfaction_surveys": 250_000,
    "digital_events": 10_000_000,
    "complaints": 80_000,
    "campaign_sends": 2_000_000,
}


def ruta(landing: str, fuente: str) -> str:
    """Ruta de lectura de una fuente: archivo suelto en la raíz o carpeta particionada."""
    base = landing.rstrip("/")
    return f"{base}/{fuente}.csv" if fuente in RAIZ else f"{base}/{fuente}/"


def opciones(fuente: str) -> dict[str, str]:
    """Opciones de Auto Loader para una fuente (ADR-23)."""
    o = {
        "cloudFiles.format": "csv",
        "header": "true",
        "multiLine": "true",          # obligatorio: textos en español con comas y saltos de línea
        "cloudFiles.schemaEvolutionMode": "addNewColumns",
        "cloudFiles.inferColumnTypes": "true",
        "rescuedDataColumn": "_rescued_data",
    }
    if fuente in HINTS:
        o["cloudFiles.schemaHints"] = HINTS[fuente]
    return o
