# Databricks notebook source
# MAGIC %md
# MAGIC # Por qué el workflow 4 · insights del dataset LATAM Bank
# MAGIC
# MAGIC Dimensión **Data Analytics** (E10). Responde tres preguntas con datos de `hackathon.gold`,
# MAGIC una figura por hallazgo:
# MAGIC
# MAGIC 1. ¿Dónde está la demanda de contacto y cuál conviene automatizar?
# MAGIC 2. ¿Quiénes son los clientes y qué tan cerca están del umbral de elegibilidad?
# MAGIC 3. ¿Qué no puede hacer el agente con este dataset?
# MAGIC
# MAGIC Fuentes: `gold.contact_demand` (E4), `gold.customer_360` (E1), `gold.customer_products` (E2).
# MAGIC Decisiones: [ADR-20](../../docs/adr/08-datos.md), [ADR-22](../../docs/adr/22-esquemas-bronze-silver.md), [ADR-23](../../docs/adr/23-verificacion-landing.md).

# COMMAND ----------

import matplotlib.pyplot as plt

CATALOG = "hackathon"
PALETA = {"foco": "#1f4e79", "resto": "#b9c6d4", "alerta": "#c0504d", "ok": "#4f8a5b"}

plt.rcParams.update({"figure.figsize": (9, 4.5), "axes.spines.top": False,
                     "axes.spines.right": False, "font.size": 10})

# Los 5 clientes de prueba TEST-* se excluyen de todo el análisis: no existen en el origen
# y contaminarían los conteos (ADR-22).
SIN_PRUEBA = "customer_id NOT LIKE 'TEST-%'"

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1 · La demanda: alto volumen y alta resolución es lo que se automatiza
# MAGIC
# MAGIC El criterio no es "automatizar lo que peor se resuelve". Una categoría que ya resuelve bien al
# MAGIC primer contacto es una consulta **estándar y repetible**, que es justo lo que un agente hace
# MAGIC bien. `Queja` resuelve mal (FCR 0,44) porque son casos que necesitan una persona: automatizarla
# MAGIC sería el error.

# COMMAND ----------

demanda = spark.sql(f"""
    SELECT reason_category,
           sum(volume)                                          AS contactos,
           round(100.0*sum(volume)/sum(sum(volume)) OVER (), 1) AS pct,
           round(avg(fcr_rate), 3)                              AS fcr,
           round(avg(csat_avg), 2)                              AS csat,
           round(avg(wait_p50_s))                               AS espera_s
    FROM {CATALOG}.gold.contact_demand
    GROUP BY 1 ORDER BY 2 DESC
""").toPandas()
display(demanda)

# COMMAND ----------

fig, ax = plt.subplots()
foco = demanda["reason_category"] == "Producto"
ax.scatter(demanda["contactos"] / 1000, demanda["fcr"],
           s=160, c=[PALETA["foco"] if f else PALETA["resto"] for f in foco], zorder=3)
for _, r in demanda.iterrows():
    ax.annotate(r["reason_category"], (r["contactos"] / 1000, r["fcr"]),
                xytext=(6, 6), textcoords="offset points",
                fontweight="bold" if r["reason_category"] == "Producto" else "normal")
ax.set_xlabel("Contacts over 3 years (thousands)")
ax.set_ylabel("First contact resolution (FCR)")
ax.set_title("Product: second by volume, among the best FCR → the one to automate")
ax.axhline(demanda["fcr"].mean(), color=PALETA["resto"], ls="--", lw=1, zorder=1)
ax.set_ylim(0.35, 1.0)
plt.tight_layout()
display(fig)

# COMMAND ----------

# MAGIC %md
# MAGIC **Hallazgo 1.** `Producto` son **150.863 contactos** (22 % del total), con FCR 0,897 y el CSAT
# MAGIC más alto junto a `Transaccional`. Son consultas estándar que hoy ya se resuelven: el agente las
# MAGIC absorbe sin tocar los casos difíciles. `Queja` (FCR 0,44) y `Técnico` (0,70) se quedan con las
# MAGIC personas, que es donde aportan.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2 · Los clientes: la mitad del segmento mayoritario no supera el umbral

# COMMAND ----------

segmentos = spark.sql(f"""
    SELECT segment,
           count(*)                   AS clientes,
           round(avg(credit_score))   AS score_medio,
           round(100.0*avg(CASE WHEN credit_score IS NULL THEN 1 ELSE 0 END), 1) AS pct_sin_score
    FROM {CATALOG}.gold.customer_360
    WHERE {SIN_PRUEBA}
    GROUP BY 1 ORDER BY 2 DESC
""").toPandas()
display(segmentos)

# COMMAND ----------

# El promedio no prueba concentración: se mide cuántos caen cerca del umbral y cuántos por debajo.
filo = spark.sql(f"""
    WITH b AS (SELECT credit_score FROM {CATALOG}.gold.customer_360
               WHERE segment = 'Basic' AND {SIN_PRUEBA} AND credit_score IS NOT NULL)
    SELECT count(*)                                                                   AS basic_con_score,
           round(100.0*avg(CASE WHEN credit_score BETWEEN 575 AND 625 THEN 1 ELSE 0 END), 1) AS pct_en_el_filo,
           round(100.0*avg(CASE WHEN credit_score < 600 THEN 1 ELSE 0 END), 1)        AS pct_bajo_umbral,
           round(percentile(credit_score, 0.10))                                      AS p10,
           round(percentile(credit_score, 0.90))                                      AS p90
    FROM b
""").toPandas()
display(filo)

# COMMAND ----------

fig, ax = plt.subplots()
UMBRAL = 600  # min_score del préstamo personal y la tarjeta en policy/catalog.yaml (E5)
colores = [PALETA["ok"] if s >= UMBRAL else PALETA["alerta"] for s in segmentos["score_medio"]]
barras = ax.barh(segmentos["segment"], segmentos["score_medio"], color=colores, zorder=3)
ax.axvline(UMBRAL, color="#333", ls="--", lw=1.5, zorder=4)
ax.text(UMBRAL + 4, -0.42, f"catalog threshold ({UMBRAL})", fontsize=9)
for b, n in zip(barras, segmentos["clientes"]):
    ax.text(b.get_width() - 12, b.get_y() + b.get_height() / 2,
            f"{n:,} customers", va="center", ha="right", color="white", fontsize=9)
ax.set_xlim(500, 830)
ax.set_xlabel("Average credit score")
ax.set_title("Basic: 60 % of the book, and half of it falls below the eligibility threshold")
plt.tight_layout()
display(fig)

# COMMAND ----------

# MAGIC %md
# MAGIC **Hallazgo 2.** `Basic` son **89.756 clientes (59,8 % de la cartera)** y su score medio es 600,
# MAGIC el umbral del catálogo. El promedio por sí solo no probaría nada, así que se mide la
# MAGIC distribución: el **47,8 % cae entre 575 y 625** —±25 puntos del umbral— y el **49,9 % queda por
# MAGIC debajo de 600**, o sea la mitad del segmento no es elegible hoy. El 80 % central va de 548 a
# MAGIC 651 (p10–p90): la masa está pegada al umbral, no repartida.
# MAGIC
# MAGIC Ahí una pre-evaluación mal calibrada se equivoca con decenas de miles de personas, y por eso el
# MAGIC pre-score es insumo del motor y **nunca decide** (ADR-06): el borde se escala a revisión humana.
# MAGIC El umbral tampoco es arbitrario, lo fijó el catálogo (E5) cruzando percentiles del dataset con
# MAGIC rangos regulatorios. Moverlo un punto mueve a miles de clientes de lado.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3 · Los límites: lo que el agente no puede hacer con este dataset

# COMMAND ----------

limites = spark.sql(f"""
    SELECT 'Clientes sin credit_score'      AS limite,
           format_number(count(CASE WHEN credit_score IS NULL THEN 1 END), 0) AS n,
           concat(round(100.0*avg(CASE WHEN credit_score IS NULL THEN 1 ELSE 0 END), 1), ' %') AS pct
    FROM {CATALOG}.gold.customer_360 WHERE {SIN_PRUEBA}
    UNION ALL
    SELECT 'Clientes sin ingreso declarado',
           format_number(count(CASE WHEN estimated_monthly_income IS NULL THEN 1 END), 0),
           concat(round(100.0*avg(CASE WHEN estimated_monthly_income IS NULL THEN 1 ELSE 0 END), 1), ' %')
    FROM {CATALOG}.gold.customer_360 WHERE {SIN_PRUEBA}
""").toPandas()
display(limites)

# COMMAND ----------

fig, ax = plt.subplots(figsize=(9, 2.6))
# Los porcentajes salen de `limites`, no escritos a mano: si cambian los datos, cambia la figura.
etiquetas = ["credit score", "declared income"]
faltan = [float(x.rstrip(" %")) for x in limites["pct"]]
ax.barh(etiquetas, [100 - f for f in faltan], color=PALETA["ok"], label="with data", zorder=3)
ax.barh(etiquetas, faltan, left=[100 - f for f in faltan], color=PALETA["alerta"],
        label="missing → human review", zorder=3)
for i, f in enumerate(faltan):
    ax.text(100 - f / 2, i, f"{f} %", va="center", ha="center", color="white", fontweight="bold")
ax.set_xlim(0, 100)
ax.set_xlabel("% of customers")
ax.set_title("One in five customers has no declared income")
ax.legend(loc="lower right", frameon=False, fontsize=9)
plt.tight_layout()
display(fig)

# COMMAND ----------

# MAGIC %md
# MAGIC **Hallazgo 3.** El **15 % no tiene `credit_score`** y el **20 % no tiene ingreso declarado**,
# MAGIC repartido por igual entre países y segmentos. No se imputan: la ausencia es señal, entra al
# MAGIC modelo como tal (ADR-23) y dispara revisión humana cuando falta el dato para simular (E12).
# MAGIC
# MAGIC Dos límites más, medidos y declarados:
# MAGIC
# MAGIC | Límite | Dato | Consecuencia |
# MAGIC | --- | --- | --- |
# MAGIC | El dataset es **100 % español** | 171.321 transcripciones, `detected_language = es` | el portugués se mide sobre corpus sintético; el clasificador solo se evalúa en ES (ADR-22) |
# MAGIC | `detected_intents` tiene **un solo valor** | `consulta_general` en el 95 %, nulo el resto | `gold.intent_labels` no es entrenable; las etiquetas se ponen a mano sobre 42 frases |
# MAGIC | Los textos son **42 frases plantilla** | sobre 171.321 filas, cada una bajo las 6 categorías | `reason_category` no correlaciona con el contenido |

# COMMAND ----------

# MAGIC %md
# MAGIC ## Resumen
# MAGIC
# MAGIC | # | Hallazgo | Qué decide |
# MAGIC | --- | --- | --- |
# MAGIC | 1 | `Producto` es el 22 % de los contactos con FCR 0,897 | el workflow 4 automatiza consultas estándar, no casos difíciles |
# MAGIC | 2 | El 48 % de Basic cae a ±25 puntos del umbral y el 50 % por debajo | el pre-score no decide; el borde se escala |
# MAGIC | 3 | 15 % sin score y 20 % sin ingreso | la ausencia es señal, no se imputa; falta de dato → revisión humana |
# MAGIC
# MAGIC Los tres sostienen la misma tesis: **el agente resuelve lo repetible y sabe cuándo no actuar.**
