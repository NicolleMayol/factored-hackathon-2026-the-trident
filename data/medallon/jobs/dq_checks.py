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

FRESCURA_MAX_H = 24  # contracts/ops.yaml · alerts.freshness_h


def _cargar_schemas(src: str | None):
    """`schemas` describe las fuentes y lo comparten el pipeline y los checks.

    En el job no se puede deducir su ruta con `__file__`: Databricks ejecuta el archivo con
    `exec(compile(...))` y ese nombre no existe. La ruta llega como parámetro `--src`, que el bundle
    resuelve por target; en local se cae al directorio hermano.
    """
    ruta = src or str(Path.cwd() / "src")
    if not Path(ruta).exists() and "__file__" in globals():
        ruta = str(Path(__file__).resolve().parents[1] / "src")
    sys.path.insert(0, ruta)
    import schemas  # noqa: PLC0415

    return schemas


def _conteo_anterior(spark, catalog, tabla) -> int | None:
    """Filas que tenía la tabla en la corrida anterior, según ops.dq_results. None la primera vez."""
    try:
        r = spark.sql(
            f"SELECT rows_checked FROM {catalog}.ops.dq_results "
            f"WHERE table = '{tabla}' AND rule = 'tabla_no_vacia' ORDER BY run_ts DESC LIMIT 1"
        ).first()
        return int(r[0]) if r else None
    except Exception:
        return None  # primera corrida: la tabla de resultados aún no existe


def check(spark, catalog, tabla, regla, condicion_mala, filas=None):
    """Cuenta las filas que violan `condicion_mala` y devuelve una fila de ops.dq_results."""
    df = spark.table(f"{catalog}.{tabla}")
    total = filas if filas is not None else df.count()
    malas = df.where(condicion_mala).count()
    return (tabla, regla, malas == 0, total, malas, None)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--catalog", default="hackathon")
    p.add_argument("--src", default=None, help="ruta de data/medallon/src (la pasa el bundle)")
    args = p.parse_args()
    cat = args.catalog
    schemas = _cargar_schemas(args.src)
    spark = SparkSession.builder.getOrCreate()
    filas: list[tuple] = []

    # ---- bronze: llegaron las 13 y en el orden de magnitud del diccionario
    for fuente in schemas.FUENTES:
        df = spark.table(f"{cat}.bronze.{fuente}")
        n = df.count()
        # El conteo del diccionario es nominal y no sirve de umbral: daily_exchange_rates tiene
        # 13.164 filas reales contra 3.000 declaradas (12 pares de divisas por día), y digital_events
        # 15,6 M contra 10 M. Comparar contra él solo medía la imprecisión del diccionario.
        # Lo que sí importa es que la tabla no se vacíe ni encoja respecto a la corrida anterior:
        # eso detecta un parseo roto o una pérdida de datos, que es el riesgo real.
        anterior = _conteo_anterior(spark, cat, f"bronze.{fuente}")
        filas.append((f"bronze.{fuente}", "tabla_no_vacia", n > 0, n, 0, None))
        filas.append((f"bronze.{fuente}", "conteo_no_cae_respecto_a_la_corrida_anterior",
                      anterior is None or n >= anterior, n, max(0, (anterior or 0) - n), None))
        # El diccionario se reporta como referencia, sin cortar.
        filas.append((f"bronze.{fuente}", "desvio_vs_diccionario", True, n,
                      abs(n - schemas.FILAS_DICCIONARIO[fuente]), None))
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
    filas.append(check(spark, cat, "gold.customer_360", "country_code_en_dominio", "country_code NOT IN ('MX','CO','AR')", n360))
    # El par country/country_code tiene que ser coherente: si se desalinean, el agente busca chunks
    # de un país y lee el perfil de otro (PR #27, opción 2).
    filas.append(check(
        spark, cat, "gold.customer_360", "country_code_coherente_con_country",
        "NOT ((country = 'Mexico' AND country_code = 'MX') OR (country = 'Colombia' AND country_code = 'CO') "
        "OR (country = 'Argentina' AND country_code = 'AR'))", n360,
    ))
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

    # ---- E5: catálogo sintético
    cat_t = spark.table(f"{cat}.gold.credit_product_catalog")
    nc = cat_t.count()
    filas.append(("gold.credit_product_catalog", "18_productos", nc == 18, nc, abs(nc - 18), None))
    filas.append(check(spark, cat, "gold.credit_product_catalog", "todo_sintetico", "es_sintetico = false OR es_sintetico IS NULL", nc))
    filas.append(check(spark, cat, "gold.credit_product_catalog", "rangos_coherentes", "rate_min > rate_max OR amount_min > amount_max", nc))
    # El join con los productos del cliente es lo que hace útil al catálogo: si product_type_dataset
    # no casa con ningún valor real, evaluate_eligibility devuelve cero sin error.
    reales = {r[0] for r in spark.table(f"{cat}.gold.customer_products").select("product_type").distinct().collect()}
    declarados = {r[0] for r in cat_t.where(F.col("product_type_dataset").isNotNull()).select("product_type_dataset").distinct().collect()}
    huerfanos = declarados - reales
    filas.append(("gold.credit_product_catalog", "product_type_dataset_casa_con_customer_products",
                  not huerfanos, len(declarados), len(huerfanos), None))

    # ---- E6: tasas de regulador
    rr = spark.table(f"{cat}.ref.regulator_rates")
    nr = rr.count()
    filas.append(check(spark, cat, "ref.regulator_rates", "rate_kind_en_dominio", "rate_kind NOT IN ('ea','tna','cat','cft','usura')", nr))
    # Deuda visible: mientras alguna fila siga sin fuente real, este check falla a propósito.
    pend = rr.where(F.col("source").startswith("PENDIENTE")).count()
    filas.append(("ref.regulator_rates", "sin_filas_PENDIENTE", pend == 0, nr, pend, None))
    filas.append(check(spark, cat, "ref.regulator_rates", "fuente_y_url_presentes",
                       "source IS NULL OR url IS NULL OR snapshot_date IS NULL", nr))
    # Cada país necesita su techo: CO usura, MX cat, AR cft (decisión de ia-ml, PR #23).
    techos = {r[0]: r[1] for r in rr.where(F.col("rate_kind").isin("usura", "cat", "cft"))
              .groupBy("country").count().collect()}
    faltan_techo = [p for p in ("CO", "MX", "AR") if techos.get(p, 0) == 0]
    filas.append(("ref.regulator_rates", "techo_por_pais", not faltan_techo, nr, len(faltan_techo), None))

    # ---- E4: demanda de contacto
    cd = spark.table(f"{cat}.gold.contact_demand")
    ncd = cd.count()
    filas.append(check(spark, cat, "gold.contact_demand", "fcr_entre_0_y_1", "fcr_rate IS NOT NULL AND (fcr_rate < 0 OR fcr_rate > 1)", ncd))
    filas.append(check(spark, cat, "gold.contact_demand", "escalados_no_superan_el_volumen", "escalated > volume", ncd))
    # El país sale de un join con customers: si hay huérfanas, caen en 'Desconocido' en vez de
    # desaparecer. Se cuentan para que la pérdida sea visible y no silenciosa.
    desc = cd.where(F.col("country") == "Desconocido").count()
    filas.append(("gold.contact_demand", "interacciones_con_pais_conocido", desc == 0, ncd, desc, None))
    # El grano es día × país × categoría: si se rompe, el notebook de insights dobla volúmenes.
    llaves = cd.select("date", "country", "reason_category").distinct().count()
    filas.append(("gold.contact_demand", "grano_unico_dia_pais_categoria", ncd == llaves, ncd, ncd - llaves, None))

    # ---- E3: etiquetas de intención
    il = spark.table(f"{cat}.gold.intent_labels")
    nil_ = il.count()
    filas.append(check(spark, cat, "gold.intent_labels", "intent_en_dominio",
                       "intent_label NOT IN ('product_info','eligibility_simulation','formal_application','disbursement','out_of_scope')", nil_))
    filas.append(check(spark, cat, "gold.intent_labels", "no_entrenable", "es_entrenable = true", nil_))
    # Sin coincidencia con ningún override: la frase queda out_of_scope, pero visible. Si crece,
    # es que el origen trae aperturas nuevas y hay que avisar a ia-ml para que amplíe docs/labels.md.
    sin_match = il.where(F.col("label_source") == "unmatched").count()
    filas.append(("gold.intent_labels", "todas_las_frases_tienen_override", sin_match == 0, nil_, sin_match, None))
    filas.append(("gold.intent_labels", "grano_unico_por_transcript_id",
                  nil_ == il.select("transcript_id").distinct().count(), nil_, 0, None))

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


# Sin `raise SystemExit`: Databricks marca la tarea como fallida aunque el código sea 0, porque
# ejecuta el archivo con exec() y la excepción sube. Los checks ya se reportan en ops.dq_results.
if __name__ == "__main__":
    main()
