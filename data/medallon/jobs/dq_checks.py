"""Checks propios de calidad → ops.dq_results (E8, segunda vía de ADR-20).

Las expectativas de SDP cortan ante fallos duros. Esto cubre lo que no expresan bien: frescura,
conteos contra el diccionario, tasas de nulos y las reglas que ADR-23 midió a mano. Registra todo
y no corta el pipeline: la alerta vive en contracts/ops.yaml (dq_failed = 1).

Esquema de salida, sin cambio (contracts/ops.yaml):
    run_ts, table, rule, passed, rows_checked, rows_failed, freshness_h
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pyspark.sql import SparkSession, functions as F

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import schemas  # noqa: E402

FRESCURA_MAX_H = 24  # contracts/ops.yaml · alerts.freshness_h


def check(spark, catalog, tabla, regla, condicion_mala, filas=None):
    """Cuenta las filas que violan `condicion_mala` y devuelve una fila de ops.dq_results."""
    df = spark.table(f"{catalog}.{tabla}")
    total = filas if filas is not None else df.count()
    malas = df.where(condicion_mala).count()
    return (tabla, regla, malas == 0, total, malas, None)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--catalog", default="hackathon")
    args = p.parse_args()
    cat = args.catalog
    spark = SparkSession.builder.getOrCreate()
    filas: list[tuple] = []

    # ---- bronze: llegaron las 13 y en el orden de magnitud del diccionario
    for fuente in schemas.FUENTES:
        df = spark.table(f"{cat}.bronze.{fuente}")
        n = df.count()
        esperado = schemas.FILAS_DICCIONARIO[fuente]
        # El diccionario es nominal (ADR-23): se alerta solo si se desvía más del 30 %, que es el
        # margen que separa "cifra redonda" de "parseo partido".
        filas.append((f"bronze.{fuente}", "conteo_en_orden_de_magnitud", abs(n - esperado) <= 0.30 * esperado, n, abs(n - esperado), None))
        frescura = df.select(F.max("_ingested_at")).first()[0]
        h = None
        if frescura is not None:
            h = float(spark.sql(f"SELECT (unix_timestamp(current_timestamp()) - unix_timestamp(timestamp'{frescura}'))/3600").first()[0])
        filas.append((f"bronze.{fuente}", "frescura", h is not None and h <= FRESCURA_MAX_H, n, 0, h))
        rescatadas = df.where(F.col("_rescued_data").isNotNull()).count()
        # No corta: una columna nueva en origen es evolución esperada (ADR-20). Se cuenta y se ve.
        filas.append((f"bronze.{fuente}", "sin_columnas_rescatadas", rescatadas == 0, n, rescatadas, None))

    # ---- silver: grano y la trampa del parseo de CSV (ADR-23)
    for fuente in schemas.A_SILVER:
        llaves = schemas.LLAVES[fuente]
        df = spark.table(f"{cat}.silver.{fuente}")
        n = df.count()
        distintas = df.select(*llaves).distinct().count()
        filas.append((f"silver.{fuente}", f"grano_unico_por_{'_'.join(llaves)}", n == distintas, n, n - distintas, None))

    # Sin multiLine, call_transcripts da 548.336 filas en vez de 171.321 y las columnas se corren.
    # Un exceso de filas sobre transcript_id distintos delata exactamente eso.
    tr = spark.table(f"{cat}.silver.call_transcripts")
    n_tr = tr.count()
    filas.append((
        "silver.call_transcripts", "parseo_multiline_correcto",
        n_tr == tr.select("transcript_id").distinct().count(), n_tr, 0, None,
    ))
    no_num = tr.where(F.col("_duration_no_numerico")).count()
    filas.append(("silver.call_transcripts", "duration_seconds_numerico", no_num == 0, n_tr, no_num, None))

    # ---- gold: contrato con ia-ml
    g360 = spark.table(f"{cat}.gold.customer_360")
    n360 = g360.count()
    filas.append(check(spark, cat, "gold.customer_360", "pais_normalizado", "country NOT IN ('Mexico','Colombia','Argentina')", n360))
    filas.append(check(spark, cat, "gold.customer_360", "credit_score_en_rango", "credit_score IS NOT NULL AND credit_score NOT BETWEEN 300 AND 850", n360))
    prueba = g360.where(F.col("customer_id").startswith("TEST-")).count()
    filas.append(("gold.customer_360", "cinco_clientes_de_prueba", prueba == 5, n360, abs(prueba - 5), None))
    # Los nulos se reportan, no se cortan: ia-ml los usa como señal (ADR-23).
    for col in ("credit_score", "estimated_monthly_income"):
        nulos = g360.where(F.col(col).isNull()).count()
        filas.append(("gold.customer_360", f"nulos_{col}", True, n360, nulos, None))

    beh = spark.table(f"{cat}.gold.customer_behavior_12m")
    nb = beh.count()
    filas.append(("gold.customer_behavior_12m", "sin_clientes_de_prueba",
                  beh.where(F.col("customer_id").startswith("TEST-")).count() == 0, nb, 0, None))
    filas.append(check(spark, cat, "gold.customer_behavior_12m", "declined_ratio_entre_0_y_1", "declined_ratio < 0 OR declined_ratio > 1", nb))

    # Columnas prohibidas: ninguna puede haber cruzado a gold (ADR-22).
    prohibidas = {"gender", "marital_status", "date_of_birth"}
    for t in ("customer_360", "customer_products", "customer_behavior_12m"):
        presentes = prohibidas & set(spark.table(f"{cat}.gold.{t}").columns)
        filas.append((f"gold.{t}", "sin_columnas_prohibidas", not presentes, 0, len(presentes), None))

    salida = (
        spark.createDataFrame(filas, "table string, rule string, passed boolean, rows_checked long, rows_failed long, freshness_h double")
        .withColumn("run_ts", F.current_timestamp())
        .select("run_ts", "table", "rule", "passed", "rows_checked", "rows_failed", "freshness_h")
    )
    salida.write.mode("append").saveAsTable(f"{cat}.ops.dq_results")

    fallidas = [f for f in filas if not f[2]]
    for f in fallidas:
        print(f"::warning::DQ falló · {f[0]} · {f[1]} · {f[4]} filas")
    print(f"{len(filas)} checks, {len(fallidas)} fallidos")
    return 0  # no corta el job: la alerta vive en contracts/ops.yaml


if __name__ == "__main__":
    raise SystemExit(main())
