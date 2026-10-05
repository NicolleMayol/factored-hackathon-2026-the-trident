"""Silver: las 7 fuentes que alimentan gold y ref (ADR-22).

Tipa, deduplica y normaliza. No agrega: eso es gold. Reglas transversales de ADR-22:
  - los nulos NO se imputan; se cuentan y se registran en ops.dq_results (E8)
  - las filas huérfanas NO se descartan; gold decide
  - ninguna columna se renombra: el nombre del diccionario es el nombre aquí

Las expectativas cortan solo ante fallos duros (llave nula, grano roto, rango imposible). Lo demás
se mide y se reporta, porque el ~2 % de duplicados y el ~5 % de nulos son parte del reto.
"""
from pyspark import pipelines as dp
from pyspark.sql import functions as F
from pyspark.sql.window import Window

import schemas

CATALOG = spark.conf.get("medallon.catalog", "hackathon")  # noqa: F821

# México llega con tilde en el origen; contracts/gold.yaml declara Mexico (ADR-23).
PAISES = {"México": "Mexico", "Mexico": "Mexico", "Colombia": "Colombia", "Argentina": "Argentina"}


def _ultima_por_llave(df, llaves: list[str], orden: str):
    """Deduplica quedándose con la fila más reciente por llave."""
    w = Window.partitionBy(*[F.col(k) for k in llaves]).orderBy(F.col(orden).desc_nulls_last())
    return df.withColumn("_rn", F.row_number().over(w)).where(F.col("_rn") == 1).drop("_rn")


def _mapa(col, mapeo: dict[str, str]):
    e = F.col(col)
    for origen, destino in mapeo.items():
        e = F.when(F.col(col) == origen, F.lit(destino)).otherwise(e)
    return e


# ------------------------------------------------------------------ dimensiones
@dp.table(name=f"{CATALOG}.silver.customers", comment="customers tipada, deduplicada y con country normalizado (ADR-22, ADR-23).")
@dp.expect_or_drop("customer_id_no_nulo", "customer_id IS NOT NULL")
@dp.expect("credit_score_en_rango", "credit_score IS NULL OR (credit_score BETWEEN 300 AND 850)")
def silver_customers():
    # Dedup por document_number, última last_updated (contracts/gold.yaml). Hoy no quita filas
    # (150.000 document_number distintos, ADR-23), pero el origen puede recargarse.
    df = spark.read.table(f"{CATALOG}.bronze.customers")
    return _ultima_por_llave(df, ["document_number"], "last_updated").withColumn("country", _mapa("country", PAISES))


@dp.table(name=f"{CATALOG}.silver.products", comment="products tipada y deduplicada por product_id (ADR-22).")
@dp.expect_or_drop("product_id_no_nulo", "product_id IS NOT NULL")
def silver_products():
    return _ultima_por_llave(spark.read.table(f"{CATALOG}.bronze.products"), ["product_id"], "last_updated")


@dp.table(name=f"{CATALOG}.silver.daily_exchange_rates", comment="Tasas de cambio diarias, 1 fila por fecha y par de monedas.")
@dp.expect_or_drop("llave_no_nula", "date IS NOT NULL AND source_currency IS NOT NULL AND target_currency IS NOT NULL")
def silver_daily_exchange_rates():
    return _ultima_por_llave(
        spark.read.table(f"{CATALOG}.bronze.daily_exchange_rates"), ["date", "source_currency", "target_currency"], "date"
    )


# ------------------------------------------------------------------ hechos
@dp.table(name=f"{CATALOG}.silver.transactions", comment="transactions deduplicada; amount_usd completado con daily_exchange_rates (ADR-22).")
@dp.expect_or_drop("transaction_id_no_nulo", "transaction_id IS NOT NULL")
def silver_transactions():
    tx = _ultima_por_llave(spark.read.table(f"{CATALOG}.bronze.transactions"), ["transaction_id"], "transaction_date")
    fx = spark.read.table(f"{CATALOG}.silver.daily_exchange_rates").where(F.col("target_currency") == "USD")
    return (
        tx.join(
            fx.select(
                F.col("date").alias("_fx_date"),
                F.col("source_currency").alias("_fx_cur"),
                F.col("exchange_rate").alias("_fx"),
            ),
            (F.to_date(tx["transaction_date"]) == F.col("_fx_date")) & (tx["currency"] == F.col("_fx_cur")),
            "left",
        )
        # Solo se completa lo ausente: si el origen ya trae amount_usd, manda el origen.
        .withColumn(
            "amount_usd",
            F.coalesce(F.col("amount_usd"), F.when(F.col("currency") == "USD", F.col("amount")).otherwise(F.col("amount") * F.col("_fx"))),
        )
        .drop("_fx_date", "_fx_cur", "_fx")
    )


@dp.table(name=f"{CATALOG}.silver.call_center_interactions", comment="Interacciones deduplicadas por interaction_id (ADR-22).")
@dp.expect_or_drop("interaction_id_no_nulo", "interaction_id IS NOT NULL")
def silver_call_center_interactions():
    return _ultima_por_llave(spark.read.table(f"{CATALOG}.bronze.call_center_interactions"), ["interaction_id"], "interaction_date")


@dp.table(name=f"{CATALOG}.silver.call_transcripts", comment="Transcripciones deduplicadas; duration_seconds casteado contando el descarte (ADR-23).")
@dp.expect_or_drop("transcript_id_no_nulo", "transcript_id IS NOT NULL")
def silver_call_transcripts():
    df = _ultima_por_llave(spark.read.table(f"{CATALOG}.bronze.call_transcripts"), ["transcript_id"], "process_date")
    return (
        # El origen escribe los enteros como decimal ("369.0"): se castea pasando por double, porque
        # try_cast("int") sobre un decimal en texto devuelve NULL. La columna auxiliar cuenta lo que
        # se pierda de verdad, sin descartar la fila.
        df.withColumn("duration_seconds_raw", F.col("duration_seconds"))
        .withColumn("duration_seconds", F.col("duration_seconds").try_cast("double").cast("int"))
        .withColumn(
            "_duration_no_numerico",
            F.col("duration_seconds").isNull() & F.col("duration_seconds_raw").isNotNull(),
        )
    )


@dp.table(name=f"{CATALOG}.silver.satisfaction_surveys", comment="Encuestas deduplicadas; main_score separado por survey_type (ADR-22).")
@dp.expect_or_drop("survey_id_no_nulo", "survey_id IS NOT NULL")
@dp.expect("score_en_rango_por_tipo",
            "main_score IS NULL "
            "OR (survey_type = 'CSAT' AND main_score BETWEEN 1 AND 5) "
            "OR (survey_type = 'NPS'  AND main_score BETWEEN 0 AND 10) "
            "OR survey_type NOT IN ('CSAT','NPS')")
def silver_satisfaction_surveys():
    df = _ultima_por_llave(spark.read.table(f"{CATALOG}.bronze.satisfaction_surveys"), ["survey_id"], "survey_date")
    return df.withColumn("csat", F.when(F.col("survey_type") == "CSAT", F.col("main_score"))).withColumn(
        "nps", F.when(F.col("survey_type") == "NPS", F.col("main_score"))
    )
