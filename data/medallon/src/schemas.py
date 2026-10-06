"""Catálogo de fuentes del medallón y hints de tipo (ADR-22, ADR-23).

Un solo sitio describe qué hay en `landing`, cómo se lee y con qué tipos. Lo usan el pipeline
(`bronze.py`) y los tests, para que el contrato no viva en dos sitios que se desincronizan.

Medido contra `landing` el 2026-10-02 (ADR-23):
  - los 7.671 archivos son CSV; no hay un solo Parquet
  - 6 CSV sueltos en la raíz (5 dimensiones + daily_exchange_rates) y 7 carpetas year=/month=/day=
  - `multiLine` es obligatorio: sin él call_transcripts da 548.336 filas en vez de 171.321
  - `escape` = comilla doble es obligatorio: sin él el JSON de mentioned_entities corre las columnas
    siguientes sin cambiar el conteo de filas (medido 2026-10-03)
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
    # Los enteros del origen vienen escritos como decimal ("209.0", "2.0"). Pedir INT en el hint hace
    # que Auto Loader no pueda castear y mande la fila entera a _rescued_data: pasó en el 86 % de
    # call_center_interactions y satisfaction_surveys en la primera corrida (2026-10-03). Entran como
    # DOUBLE y es silver quien aplica el tipo del contrato.
    "call_center_interactions": "duration_seconds DOUBLE, wait_time_seconds DOUBLE, sentiment_score DECIMAL(3,2)",
    "call_transcripts": "duration_seconds DOUBLE, accent_confidence DECIMAL(3,2)",
    "satisfaction_surveys": "main_score DOUBLE, question_1_response DOUBLE, question_2_response DOUBLE, question_3_response DOUBLE",
    "daily_exchange_rates": "exchange_rate DECIMAL(12,6), buy_rate DECIMAL(12,6), sell_rate DECIMAL(12,6)",
}

# Acción por intent (policy/policy.yaml, vía docs/labels.md de ia-ml). `out_of_scope → clarify`:
# la frase se entiende, pero queda fuera del workflow 4 y se pide precisión.
ACCION_POR_INTENT = {
    "product_info": "answer",
    "eligibility_simulation": "confirm",
    "formal_application": "escalate",
    "disbursement": "escalate",
    "out_of_scope": "clarify",
}

_INTENTS = "|".join(ACCION_POR_INTENT)


def overrides_de_labels(texto_md: str) -> dict[str, str]:
    """Lee la tabla "Overrides" de docs/labels.md: | frase | intent |.

    La regla de etiquetado es de ia-ml (M5) y vive en ese documento; el pipeline la aplica en vez de
    copiarla, para que añadir un override no obligue a tocar dos sitios. Mismo formato que lee
    `ml/label_phrases.py`.
    """
    import re

    fuera, pares = False, {}
    for linea in texto_md.splitlines():
        if linea.startswith("## Overrides"):
            fuera = True
            continue
        if fuera and linea.startswith("## ") :
            break
        if not fuera:
            continue
        m = re.match(rf"\|\s*(.+?)\s*\|\s*({_INTENTS})\s*\|", linea)
        if m and m.group(1) != "customer_text":
            pares[m.group(1)] = m.group(2)
    return pares


# Las tablas del agente usan ISO-2 (credit_product_catalog, ref.regulator_rates, policy_chunks) y
# customer_360 usa el nombre completo. country_code elimina la traducción (PR #27, opción 2 de ia-ml).
CODIGO_PAIS = {"Mexico": "MX", "Colombia": "CO", "Argentina": "AR"}

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


def opciones(fuente: str, streaming: bool = True) -> dict[str, str]:
    """Opciones de lectura de una fuente (ADR-23).

    `streaming=True` da las de Auto Loader, para las 7 particionadas. `streaming=False` da las
    equivalentes del lector en lote, para las 6 de la raíz: Auto Loader exige un directorio y esas
    son archivos sueltos (`CloudInvalidPathException: Input path is not a directory`).
    """
    o = {
        "cloudFiles.format": "csv",
        "header": "true",
        "multiLine": "true",          # obligatorio: textos en español con comas y saltos de línea
        # Obligatorio también: los archivos escapan las comillas internas duplicándolas (RFC-4180),
        # pero Spark usa "\\" por defecto. Sin esto, toda fila con un JSON embebido corre sus
        # columnas en silencio: call_transcripts.mentioned_entities se partía en detected_intents,
        # main_topics y transcription_model. El conteo de filas no cambia, así que no se nota.
        "escape": '"',
        "cloudFiles.schemaEvolutionMode": "addNewColumns",
        "cloudFiles.inferColumnTypes": "true",
        "rescuedDataColumn": "_rescued_data",
    }
    if fuente in HINTS:
        o["cloudFiles.schemaHints"] = HINTS[fuente]
    if streaming:
        return o
    # Lector en lote: mismas opciones sin el prefijo cloudFiles, y la inferencia se pide con
    # inferSchema. Los hints no existen fuera de Auto Loader; el tipado lo hace silver.
    lote = {k.removeprefix("cloudFiles."): v for k, v in o.items() if not k.startswith("cloudFiles.schema")}
    for solo_autoloader in ("format", "inferColumnTypes"):
        lote.pop(solo_autoloader, None)
    lote["inferSchema"] = "true"
    return lote
