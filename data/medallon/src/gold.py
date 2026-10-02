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
import dlt
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


@dlt.table(
    name=f"{CATALOG}.gold.customer_360",
    comment="1 fila por customer_id. Sin gender, marital_status ni date_of_birth (excluded_from_features). Incluye los 5 TEST-* de docs/test-users.md.",
)
@dlt.expect_or_fail("customer_id_no_nulo", "customer_id IS NOT NULL")
@dlt.expect("pais_normalizado", "country IN ('Mexico', 'Colombia', 'Argentina')")
@dlt.expect("country_code_valido", "country_code IN ('MX', 'CO', 'AR')")
def gold_customer_360():
    codigo = F.create_map([F.lit(x) for kv in schemas.CODIGO_PAIS.items() for x in kv])
    reales = dlt.read(f"{CATALOG}.silver.customers").select(
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
            "customer_id string, country string, country_code string, segment string, credit_score int, "
            "estimated_monthly_income decimal(12,2), customer_status string, registration_date string, detected_accent string",
        )
        .withColumn("registration_date", F.to_timestamp("registration_date"))
        .withColumn("_ingested_at", F.current_timestamp())
    )
    return reales.unionByName(prueba.select(*reales.columns))


@dlt.table(name=f"{CATALOG}.gold.customer_products", comment="1 fila por product_id (contracts/gold.yaml).")
@dlt.expect_or_fail("product_id_no_nulo", "product_id IS NOT NULL")
def gold_customer_products():
    return dlt.read(f"{CATALOG}.silver.products").select(
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


@dlt.table(
    name=f"{CATALOG}.gold.customer_behavior_12m",
    comment=f"1 fila por customer_id. Ventana de 12 meses hasta el corte {CORTE} (contracts/gold.yaml). Sin los TEST-*.",
)
@dlt.expect_or_fail("customer_id_no_nulo", "customer_id IS NOT NULL")
@dlt.expect("ratio_entre_0_y_1", "declined_ratio BETWEEN 0 AND 1")
def gold_customer_behavior_12m():
    # Los clientes de prueba no entran a ninguna agregación (ADR-22): no existen en el origen y
    # contaminarían conteos y ratios.
    tx = (
        dlt.read(f"{CATALOG}.silver.transactions")
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
        dlt.read(f"{CATALOG}.silver.products")
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
