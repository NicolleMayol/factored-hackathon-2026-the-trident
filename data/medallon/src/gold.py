"""Gold: las tablas de `contracts/gold.yaml` que consume el agente.

Este archivo cubre E1 y E2: `customer_360`, `customer_products` y `customer_behavior_12m`.
`intent_labels` (E3), `contact_demand` (E4), `credit_product_catalog` (E5) y `ref.regulator_rates`
(E6) van en el siguiente incremento.

Reglas que vienen del contrato y de los ADR:
  - `gender`, `marital_status` y `date_of_birth` no cruzan a gold (`excluded_from_features`, ADR-22)
  - corte de comportamiento: 2025-06-30, ventana de 12 meses (contracts/gold.yaml)
  - los 5 clientes TEST-* se inyectan SOLO aquí y quedan fuera de toda agregación (ADR-22)
  - los nulos de credit_score y estimated_monthly_income NO se imputan: ia-ml los usa como señal
    con flags propios (ADR-23, respuesta de ia-ml en el PR #25)
"""
from pyspark import pipelines as dp
from pyspark.sql import functions as F

import schemas

CATALOG = spark.conf.get("medallon.catalog", "hackathon")  # noqa: F821

CORTE = "2025-06-30"                    # contracts/gold.yaml · gold.customer_behavior_12m.cutoff_date
VENTANA_INICIO = "2024-07-01"           # 12 meses hasta el corte
PREFIJO_PRUEBA = "TEST-"                # ADR-22: así se reconocen y así se excluyen

# Los 5 clientes de prueba de docs/test-users.md (M3). Van literales porque son el contrato con
# ia-ml y servicio, no un dato del origen; el dataset no los contiene.
CLIENTES_PRUEBA = [
    ("TEST-CO-001", "Colombia", "CO", "Premium", 780, 9_500_000.00, "Active", "2021-03-01", "colombian"),
    ("TEST-MX-002", "Mexico", "MX", "Plus", 650, 18_000.00, "Active", "2021-03-01", "mexican"),
    ("TEST-AR-003", "Argentina", "AR", "Plus", 590, 900_000.00, "Active", "2021-03-01", "argentine"),
    ("TEST-CO-004", "Colombia", "CO", "Premium", 760, 8_200_000.00, "Active", "2021-03-01", "colombian"),
    ("TEST-MX-005", "Mexico", "MX", "Basic", 700, 15_000.00, "Active", "2021-03-01", "mexican"),
]


@dp.table(
    name=f"{CATALOG}.gold.customer_360",
    comment="1 fila por customer_id. Sin gender, marital_status ni date_of_birth (excluded_from_features). Incluye los 5 TEST-* de docs/test-users.md.",
)
@dp.expect_or_fail("customer_id_no_nulo", "customer_id IS NOT NULL")
@dp.expect("pais_normalizado", "country IN ('Mexico', 'Colombia', 'Argentina')")
@dp.expect("country_code_valido", "country_code IN ('MX', 'CO', 'AR')")
def gold_customer_360():
    codigo = F.create_map([F.lit(x) for kv in schemas.CODIGO_PAIS.items() for x in kv])
    reales = spark.read.table(f"{CATALOG}.silver.customers").select(
        F.col("customer_id").cast("string"),
        F.col("country").cast("string"),
        codigo[F.col("country")].alias("country_code"),
        F.col("segment").cast("string"),
        F.col("credit_score").cast("int"),
        F.col("estimated_monthly_income").cast("decimal(12,2)"),
        F.col("customer_status").cast("string"),
        F.col("registration_date").cast("timestamp"),
        F.col("detected_accent").cast("string"),
        F.col("_ingested_at").cast("timestamp"),
    )
    prueba = (
        spark.createDataFrame(  # noqa: F821
            CLIENTES_PRUEBA,
            # Tipos simples: createDataFrame no acepta un float de Python en una columna decimal.
            # El tipado definitivo se aplica abajo, copiándolo de `reales` para que no puedan diferir.
            "customer_id string, country string, country_code string, segment string, credit_score int, "
            "estimated_monthly_income double, customer_status string, registration_date string, detected_accent string",
        )
        .withColumn("registration_date", F.to_timestamp("registration_date"))
        .withColumn("_ingested_at", F.current_timestamp())
    )
    prueba = prueba.select([F.col(c).cast(reales.schema[c].dataType) for c in reales.columns])
    return reales.unionByName(prueba)


@dp.table(name=f"{CATALOG}.gold.customer_products", comment="1 fila por product_id (contracts/gold.yaml).")
@dp.expect_or_fail("product_id_no_nulo", "product_id IS NOT NULL")
def gold_customer_products():
    return spark.read.table(f"{CATALOG}.silver.products").select(
        F.col("product_id").cast("string"),
        F.col("customer_id").cast("string"),
        F.col("product_type").cast("string"),
        F.col("currency").cast("string"),
        F.col("current_balance").cast("decimal(15,2)"),
        F.col("credit_limit").cast("decimal(15,2)"),
        F.col("days_past_due").cast("int"),
        F.col("product_status").cast("string"),
        F.col("_ingested_at").cast("timestamp"),
    )


@dp.table(
    name=f"{CATALOG}.gold.customer_behavior_12m",
    comment=f"1 fila por customer_id. Ventana de 12 meses hasta el corte {CORTE} (contracts/gold.yaml). Sin los TEST-*.",
)
@dp.expect_or_fail("customer_id_no_nulo", "customer_id IS NOT NULL")
@dp.expect("ratio_entre_0_y_1", "declined_ratio BETWEEN 0 AND 1")
def gold_customer_behavior_12m():
    # Los clientes de prueba no entran a ninguna agregación (ADR-22): no existen en el origen y
    # contaminarían conteos y ratios.
    tx = (
        spark.read.table(f"{CATALOG}.silver.transactions")
        .where(F.col("process_date").between(F.lit(VENTANA_INICIO), F.lit(CORTE)))
        .where(~F.col("customer_id").startswith(PREFIJO_PRUEBA))
    )
    comportamiento = tx.groupBy("customer_id").agg(
        F.count("*").cast("int").alias("n_tx"),
        F.sum("amount_usd").cast("decimal(15,2)").alias("amount_usd_12m"),
        F.avg(F.when(F.col("transaction_status") == "Declined", 1.0).otherwise(0.0))
        .cast("decimal(5,4)")
        .alias("declined_ratio"),
        F.countDistinct(F.date_trunc("month", F.col("process_date"))).cast("int").alias("active_months"),
    )
    # max_days_past_due vive en products, no en transactions (diccionario de Factored).
    mora = (
        spark.read.table(f"{CATALOG}.silver.products")
        .where(~F.col("customer_id").startswith(PREFIJO_PRUEBA))
        .groupBy("customer_id")
        .agg(F.max("days_past_due").cast("int").alias("max_days_past_due"))
    )
    return (
        comportamiento.join(mora, "customer_id", "left")
        .withColumn("_ingested_at", F.current_timestamp())
        .select(
            "customer_id", "n_tx", "amount_usd_12m", "declined_ratio",
            "max_days_past_due", "active_months", "_ingested_at",
        )
    )


# ------------------------------------------------------------------ E5 y E6: insumos de ref
# No salen del dataset: son el catálogo sintético (ADR-12) y las tasas de regulador. El repo es la
# fuente de verdad y `bundles.yml` los copia al volumen; el pipeline lee el volumen, nunca la API
# ni el repo, para que una corrida sea reproducible y fechada (ADR-12: batch versionado).
VOL_FUENTES = "/Volumes/hackathon/ref/fuentes"


@dp.table(
    name=f"{CATALOG}.gold.credit_product_catalog",
    comment="Catálogo sintético (E5). AR del BCRA, CO y MX de percentiles del dataset. es_sintetico = true.",
)
@dp.expect_or_fail("product_code_no_nulo", "product_code IS NOT NULL")
@dp.expect("todo_sintetico", "es_sintetico = true")
@dp.expect("rango_de_tasa_coherente", "rate_min <= rate_max")
@dp.expect("rango_de_monto_coherente", "amount_min <= amount_max")
def gold_credit_product_catalog():
    # El YAML del catálogo se carga como texto y se explota: así una fila mal formada no tumba el
    # pipeline entero y queda visible en el check de conteo.
    df = spark.read.format("text").option("wholetext", "true").load(f"{VOL_FUENTES}/catalog.yaml")  # noqa: F821
    import yaml  # local: el intérprete del pipeline lo trae

    productos = yaml.safe_load(df.first()["value"])["products"]
    return (
        spark.createDataFrame(productos)  # noqa: F821
        .select(
            F.col("product_code").cast("string"),
            F.col("country").cast("string"),
            F.col("name_es").cast("string"),
            F.col("name_pt").cast("string"),
            F.col("product_type").cast("string"),
            F.col("product_type_dataset").cast("string"),
            F.col("min_score").cast("int"),
            F.col("currency").cast("string"),
            F.col("rate_min").cast("decimal(5,2)"),
            F.col("rate_max").cast("decimal(5,2)"),
            F.col("amount_min").cast("decimal(15,2)"),
            F.col("amount_max").cast("decimal(15,2)"),
            F.col("term_months_max").cast("int"),
            F.col("requirements").cast("string"),
            F.col("valid_from").cast("date"),
            F.col("valid_to").cast("date"),
            F.col("es_sintetico").cast("boolean"),
        )
        .withColumn("_ingested_at", F.current_timestamp())
    )


@dp.table(
    name=f"{CATALOG}.ref.regulator_rates",
    comment="Tasas de regulador por país, producto y tipo de tasa (E6). Techo legal del motor; no es oferta.",
)
@dp.expect_or_fail("llave_no_nula", "country IS NOT NULL AND product_type IS NOT NULL AND rate_kind IS NOT NULL")
@dp.expect("rate_kind_en_dominio", "rate_kind IN ('ea','tna','cat','cft','usura')")
def ref_regulator_rates():
    # Se lee el snapshot más reciente del volumen. Varios snapshots conviven a propósito: una
    # respuesta citada en octubre tiene que poder reproducirse con la tasa de octubre.
    return (
        spark.read.format("csv")  # noqa: F821
        .option("header", "true").option("multiLine", "true")
        .load(f"{VOL_FUENTES}/regulator_rates_*.csv")
        .select(
            F.col("country").cast("string"),
            F.col("product_type").cast("string"),
            F.col("rate_kind").cast("string"),
            F.col("rate_min").cast("decimal(5,2)"),
            F.col("rate_max").cast("decimal(5,2)"),
            F.col("source").cast("string"),
            F.col("url").cast("string"),
            F.col("snapshot_date").cast("date"),
        )
        .withColumn("_ingested_at", F.current_timestamp())
    )


@dp.table(
    name=f"{CATALOG}.gold.contact_demand",
    comment="Demanda de contacto por día, país y categoría (E4). Alimenta el notebook de insights (E10) y el pitch.",
)
@dp.expect_or_fail("llave_no_nula", "date IS NOT NULL AND country IS NOT NULL AND reason_category IS NOT NULL")
@dp.expect("fcr_entre_0_y_1", "fcr_rate IS NULL OR fcr_rate BETWEEN 0 AND 1")
@dp.expect("escalados_no_superan_el_volumen", "escalated <= volume")
def gold_contact_demand():
    # El país no está en la interacción: sale del cliente. Las interacciones sin cliente conocido
    # (huérfanas, que el diccionario admite) se cuentan aparte y no se descartan en silencio.
    inter = spark.read.table(f"{CATALOG}.silver.call_center_interactions")
    clientes = spark.read.table(f"{CATALOG}.silver.customers").select("customer_id", "country")

    # CSAT: solo las encuestas de tipo CSAT puntúan 1–5. Las NPS van de 0 a 10 y promediarlas
    # juntas daría un número sin significado.
    csat = (
        spark.read.table(f"{CATALOG}.silver.satisfaction_surveys")
        .where(F.col("survey_type") == "CSAT")
        .groupBy("interaction_id")
        .agg(F.avg("main_score").alias("_csat"))
    )

    return (
        inter.join(clientes, "customer_id", "left")
        .join(csat, "interaction_id", "left")
        .withColumn("country", F.coalesce(F.col("country"), F.lit("Desconocido")))
        .groupBy(F.col("process_date").alias("date"), "country", "reason_category")
        .agg(
            F.count("*").cast("int").alias("volume"),
            # fcr_rate solo sobre las que declaran resolución: contar un nulo como no resuelto
            # inventaría un FCR más bajo del real.
            F.avg(F.when(F.col("was_resolved").isNotNull(), F.col("was_resolved").cast("double")))
             .cast("decimal(5,4)").alias("fcr_rate"),
            F.sum(F.when(F.col("was_escalated"), 1).otherwise(0)).cast("int").alias("escalated"),
            F.percentile_approx("wait_time_seconds", 0.5).cast("int").alias("wait_p50_s"),
            F.avg("_csat").cast("decimal(3,2)").alias("csat_avg"),
        )
        .withColumn("_ingested_at", F.current_timestamp())
    )
