# data/medallon · Asset Bundle del medallón (datos)

Pipeline declarativo bronze → silver → gold sobre Unity Catalog, más el job de calidad.
Decisiones: [ADR-20](../../docs/adr/08-datos.md) (plataforma e ingesta), [ADR-22](../../docs/adr/22-esquemas-bronze-silver.md) (contrato de capas), [ADR-23](../../docs/adr/23-verificacion-landing.md) (el origen es CSV).

```
data/medallon/
  databricks.yml        bundle; target prod corre como sp-pipelines (X2)
  resources/
    pipeline.yml        pipeline SDP serverless, catálogo hackathon
    job.yml             pipeline + checks de DQ, cada 6 h al minuto 50
  src/
    schemas.py          qué hay en landing, cómo se lee y con qué hints
    bronze.py           las 13 fuentes 1:1
    silver.py           las 7 que alimentan gold: tipado, dedup, normalización
    gold.py             customer_360, customer_products, customer_behavior_12m (E1, E2)
  jobs/
    dq_checks.py        checks propios → ops.dq_results (E8, segunda vía)
```

## Cómo se lee `landing`
El dataset es **CSV**, no Parquet, y está en dos formas (ADR-23):

| | Fuentes | Ruta |
| --- | --- | --- |
| Archivo suelto | `customers`, `products`, `branches`, `service_agents`, `marketing_campaigns`, `daily_exchange_rates` | `data/<tabla>.csv` |
| Carpeta particionada | los 7 hechos | `data/<tabla>/year=YYYY/month=MM/day=DD/` |

`multiLine` no es opcional: sin él `call_transcripts` devuelve 548.336 filas en vez de 171.321, con JSON de `mentioned_entities` desbordado en `detected_language`. **El pipeline no falla, entrega basura**, y por eso hay un test (`tests/test_medallon.py`) y un check de DQ que lo vigilan.

## Alcance de cada capa
- **bronze**: las 13 fuentes 1:1, más `_ingested_at`, `_source_file` y `_rescued_data`. Sin reglas de negocio.
- **silver**: las 7 que alimentan gold y ref. Tipa, deduplica y normaliza `country` (el origen trae `México` con tilde). No agrega. Los nulos no se imputan y las huérfanas no se descartan: se cuentan.
- **gold**: las tablas de `contracts/gold.yaml`. Los 5 clientes `TEST-*` se inyectan solo aquí y quedan fuera de toda agregación.

`digital_events`, `campaign_sends` y `complaints` se quedan en bronze: 12,08 M de filas que no alimentan ninguna tabla gold del workflow 4.

## Correr
```bash
cd data/medallon
databricks bundle validate -t dev      # lo mismo que corre el PR
databricks bundle deploy   -t dev      # despliega bajo tu usuario, sin tocar prod
databricks bundle run medallon_job -t dev
```
CI lo hace solo: `bundles.yml` valida en cada PR que toca `data/**` y despliega a `prod` en `main`.

Los tests no necesitan Spark ni workspace:
```bash
pytest tests/test_medallon.py -q
```

## Pendiente
- `gold.intent_labels` (E3), `gold.contact_demand` (E4), `gold.credit_product_catalog` (E5) y `ref.regulator_rates` (E6).
- `rate_kind` entra al contrato con E6, con el dominio que fijó ia-ml: `[ea, tna, cat, cft, usura]`. Hasta entonces el test de cabeceras lo lleva como excepción documentada.
