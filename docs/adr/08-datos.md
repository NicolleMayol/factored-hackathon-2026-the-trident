# 08-datos

Owner: Eladio · v2 · 2026-09-30.

## ADR-20 · Plataforma de datos e ingesta  ·  rol: datos  ·  2026-09-30  ·  estado: cerrada

**Decisión.** El medallón corre en Spark Declarative Pipelines sobre Unity Catalog, con un container y una external location por esquema, y la ingesta es Auto Loader en modo file events desde el contenedor `landing` (Parquet), con calidad en dos vías hacia `ops.dq_results`.

### Qué pide esta decisión a servicio
Datos no crea recursos (ADR-19). Esta es la lista completa de lo que hace falta para que exista el medallón.

| # | Recurso o permiso | Nombre | Para qué |
| --- | --- | --- | --- |
| 1 | Catálogo y esquemas en Unity Catalog | `hackathon` · `bronze`, `silver`, `gold`, `ref`, `ops`, `ml` | sin esto no hay dónde crear tablas |
| 2 | Containers en `adlsagentbankdev`, uno por esquema y con el mismo nombre | `bronze`, `silver`, `gold`, `ref`, `ops`, `ml` | managed location por esquema; frontera de permisos por capa |
| 3 | Storage credential | `stg-credential-adlsagentbankdev` | identidad de Unity Catalog sobre ADLS |
| 4 | External locations, una por container más `landing` | `ext-loc-adlsagentbankdev-{bronze,silver,gold,ref,ops,ml,landing}` | managed location de cada esquema y lectura del dataset |
| 5 | Roles del Access Connector `acc-agent-bank-dev` sobre `adlsagentbankdev` | Storage Account Contributor · Storage Blob Data Contributor · EventGrid EventSubscription Contributor · Storage Queue Data Contributor | los cuatro que exige Auto Loader en file events: Databricks crea la suscripción de Event Grid y la Storage Queue por external location. Hoy solo tiene el segundo |
| 6 | `ALL PRIVILEGES` sobre todos los objetos de Databricks | Eladio y `sp-pipelines` | trabajar sin pedir un grant por tabla |
| 7 | Volumen de Unity Catalog | `policy_docs` ES+PT, fuentes de `ref`, checkpoints de Auto Loader | insumos y estado del pipeline, que no van al repo |
| 8 | SQL Warehouse | `CAN_USE` en `wh-agent` para Eladio y `sp-pipelines` | validar tablas y correr los checks de calidad |
| 9 | Workflow de despliegue | `bundles.yml` con `run_as = sp-pipelines` (X2) | desplegar los Asset Bundles de `data/` |
| 10 | Lectura del secret scope `fh26` (`cosmos-key`) | `sp-pipelines` | E7 carga el JSONL de chunks a Cosmos |
| 11 | Confirmación del SKU `trial` | cobertura de serverless, SDP, Model Serving y FM APIs | sin cómputo serverless no corre ningún pipeline |

Nicolle tiene account admin de Databricks desde el 2026-09-29, así que `infra/databricks` ya no está bloqueado por permisos. Quedan obsoletas las notas que dicen lo contrario en `contracts/infra.yaml`, `infra/README.md` y `docs/adr/09-servicio.md`.

### Ingesta
Fuente efectiva: `abfss://landing@adlsagentbankdev.dfs.core.windows.net/factored-datathon/data/`, que puebla el workflow `data-landing` con `azcopy` cada 6 h al minuto 17. Carga inicial del 2026-09-30: 7.671 archivos, 5.349.322.481 bytes, 0 fallas. Databricks no lee S3: Unity Catalog en Azure no toma llaves de S3 y serverless no deja ponerlas en la config de Spark (ADR-19).

| Parámetro | Valor | Por qué |
| --- | --- | --- |
| `cloudFiles.format` | `parquet` | formato del dataset; autodescriptivo, sin schema hints |
| Descubrimiento | file events gestionados | con 7.671 archivos, el directory listing domina costo y latencia en cada corrida |
| Checkpoint y schema location | volumen de Unity Catalog | no se mezcla el estado del pipeline con los datos |
| Evolución de esquema | `addNewColumns` + `_rescued_data` preservada en bronze | una columna nueva en origen no detiene la corrida y queda registrada |
| Horario | cada 6 h al minuto 50 | 33 min después de `data-landing` (:17), para leer la copia ya cerrada |
| Partición | ninguna | 5,35 GB no la justifica; liquid clustering si una tabla lo pide |

Capas: `bronze` es 1:1 con el archivo origen más `_ingested_at`, `_rescued_data` y la ruta del archivo, sin reglas de negocio. `silver` tipa, deduplica (`document_number`, último `last_updated`) y normaliza país e idioma. `gold` y `ref` son las 7 tablas de `contracts/gold.yaml`, sin cambio de contrato. En `ops` solo escribo `ops.dq_results`: `ops.agent_turns` y `ops.ml_inference` son de ia-ml y `ops.infra_requests` de servicio, y aunque los grants del punto 6 lo permitan, no los toco.

### Calidad y frescura
Dos vías, una sola tabla de salida, sin cambio en `contracts/ops.yaml`.

| Vía | Qué cubre | Efecto al fallar |
| --- | --- | --- |
| Expectativas de SDP | llave nula, grano roto, `credit_score` fuera de 300–850, tipos | corta el pipeline |
| Checks propios al cierre del job | frescura, conteos y reglas de negocio que las expectativas no expresan | registra y dispara alerta |

Las dos escriben `ops.dq_results` con su esquema actual (`run_ts`, `table`, `rule`, `passed`, `rows_checked`, `rows_failed`, `freshness_h`). Frescura máxima 24 h y alerta `dq_failed = 1`, los umbrales que ya están en `contracts/ops.yaml`.

### Llegada tardía y evolución de esquema
Sin fixture sintético: el manifiesto `_manifest/manifest-<fecha>.json` de `data-landing` ya lista `new` y `changed` contra la corrida anterior. El fixture de E8 se arma tomando un manifiesto con `new` no vacío y reprocesando con Auto Loader, y se verifica que las filas nuevas entren sin duplicar las anteriores.

### Leakage
Corte 2025-06-30 en `gold.customer_behavior_12m`. Columnas prohibidas en features: `gender`, `marital_status`, `date_of_birth`, ya declaradas como `excluded_from_features` en `contracts/gold.yaml`. El split de `gold.intent_labels` es temporal por `process_date`, con los últimos 3 meses a test.

### Fuentes externas
| Fuente | URL | Formato | Licencia | Llave | `es_sintetico` |
| --- | --- | --- | --- | --- | --- |
| Dataset de Factored (S3) | `https://factored-datathon-2026-s3-157725502942-us-east-2-an.s3.us-east-2.amazonaws.com/data` | Parquet | dataset del reto, uso limitado al hackathon | sí: `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, solo como secretos de GitHub | false |
| SFC Colombia | pendiente de registrar con fecha de snapshot (E6) | — | publicación pública | no | false |
| Banxico y CONDUSEF México | pendiente de registrar con fecha de snapshot (E6) | — | publicación pública | no | false |
| BCRA Argentina | pendiente de registrar con fecha de snapshot (E6) | — | publicación pública | no | false |
| `gold.credit_product_catalog` | sintético propio (E5) | — | — | no | **true** |

Ninguna fuente se consulta en vivo (ADR-12). Ningún dato del dataset entra al repo: las fuentes de `ref` y los `policy_docs` van al volumen de Unity Catalog.

### Decisiones abiertas
| # | Qué | Dueño | Cuándo |
| --- | --- | --- | --- |
| 1 | Contrato de columnas de bronze y silver: se congela tras inspeccionar `landing` (E9) | datos | jue 1 |
| 2 | `ml.embeddings_endpoint`: `contracts/chunks.yaml` fija bge-m3 de 1024 dims, no existe endpoint en `infra.yaml` `fm_apis` y bge-m3 no es un modelo de FM APIs | a definir con ia-ml | jue 1 |
| 3 | Cobertura del SKU `trial` para serverless, SDP, Model Serving y FM APIs | servicio | mié 30 |

| Alternativas descartadas | Por qué |
| --- | --- |
| Jobs con notebooks PySpark para el medallón | sin linaje ni expectativas nativas; la calidad habría que construirla a mano |
| Auto Loader en directory listing | 7.671 archivos por corrida: el listado domina costo y latencia |
| Leer S3 directo desde Databricks serverless | Unity Catalog en Azure no toma llaves de S3 y serverless no deja ponerlas en la config de Spark (ADR-19) |
| Un solo container para los 6 esquemas | sin frontera de permisos por capa; el managed location por esquema la da sin trabajo extra |
| Checkpoint en el container de datos | mezcla estado del pipeline con datos; borrar el container se lleva el checkpoint |
| Fixture sintético de llegada tardía | el manifiesto de `data-landing` ya da evidencia real |
| Partición de bronze por fecha | 5,35 GB no la justifica |
| Congelar bronze y silver hoy | las columnas saldrían del diccionario de datos y no de los archivos |

**Impacto.**

| Elemento | Estado | Owner | Consumers afectados | Qué deben hacer | Fecha límite |
| --- | --- | --- | --- | --- | --- |
| `infra.adls` | cambia: +6 containers (`bronze`…`ml`), storage credential `stg-credential-adlsagentbankdev`, 4 roles al Access Connector | servicio | datos, ia-ml | Nicolle: aplicar en `infra/databricks`; el rol extra en `infra/azure` | mié 30 |
| `infra.uc_external_locations` | nuevo: 7 × `ext-loc-adlsagentbankdev-{esquema\|landing}` | servicio | datos, ia-ml | Nicolle: crear con esa nomenclatura; managed location por esquema | mié 30 |
| `infra.uc_volumes` | nuevo: `policy_docs`, fuentes de `ref`, checkpoints de Auto Loader | servicio | datos, ia-ml | Nicolle: crear y dar escritura a `sp-pipelines` | mié 30 |
| `infra.databricks_access` | cambia: `ALL PRIVILEGES` a datos y a `sp-pipelines` sobre todos los objetos; `CAN_USE` en `wh-agent` | servicio | datos, ia-ml | Nicolle: aplicar grants | mié 30 |
| `infra.databricks_workspace` | cambia: confirmar cobertura de serverless y SDP en el SKU `trial` | servicio | datos, ia-ml | Nicolle: confirmar o escalar el SKU | mié 30 |
| `infra.key_vault` | cambia: lectura del scope `fh26` (`cosmos-key`) para `sp-pipelines` | servicio | datos, ia-ml | Nicolle: grant de lectura | jue 1 |
| `infra.ci_cd` | cambia: `bundles.yml` con `run_as = sp-pipelines` | servicio | datos, ia-ml | Nicolle: crear el workflow | mié 30 |
| `data.source_s3` | cambia: Databricks ya no lee S3; la fuente efectiva es `landing` | datos | — | nada | — |
| `data.ingest_s3` | cambia: Auto Loader en SDP desde `landing`, Parquet, file events, checkpoint en volumen | datos | — | nada | — |
| `data.pipeline_medallon` | cambia: SDP declarativo en las tres capas; DQ en dos vías | datos | ia-ml | Manuela: nada en código; el contrato de gold no cambia | — |
| `ops.dq_results` | cambia: se puebla desde expectativas de SDP y desde checks propios; esquema sin cambio | datos | servicio | Nicolle: la alerta `dq_failed = 1` sigue igual | vie 2 |
| `ml.embeddings_endpoint` | nuevo, abierta: bge-m3 de `chunks.yaml` no existe en `fm_apis` | a definir | datos, servicio | Manuela: decidir si va en Model Serving o dentro del job de E7 | jue 1 |
| `gold.*` (7 tablas) | existe, sin cambio de esquema | datos | ia-ml | nada | — |
| `contracts/gold.yaml` v1 → v2 | cambia: añade el bloque `source` (landing, Parquet, Auto Loader, horario) y la decisión abierta de bronze/silver | datos | ia-ml | Manuela: ninguna acción; las columnas de gold son las mismas | — |

**Cómo se prueba.**

| Prueba | Umbral | Dónde se registra |
| --- | --- | --- |
| Auto Loader en file events procesa solo lo nuevo | archivos procesados = `new` + `changed` del manifiesto de `data-landing` | log del job + `ops.dq_results` |
| Expectativas de SDP en las tres capas | 0 violaciones duras | evento del pipeline → `ops.dq_results` |
| Frescura de gold | ≤ 24 h | `ops.dq_results.freshness_h`; alerta de `contracts/ops.yaml` |
| Grano y llave de las 7 tablas gold | 0 duplicados por llave | `ops.dq_results` |
| Leakage | 0 filas con `process_date` posterior al corte en train; 0 columnas prohibidas en features | `ops.dq_results` |
| Reproceso de un manifiesto con `new` no vacío | las filas nuevas entran sin duplicar las anteriores | E8 |
| `sp-pipelines` escribe en los 6 esquemas | `CREATE TABLE` pasa en los 6 | CI (test SQL) |
| Costo del medallón | se mide a diario | `system.billing.usage` |

**Hackathon vs To-Be.**

| Hackathon | To-Be |
| --- | --- |
| SDP cada 6 h por horario | Lakeflow con trigger por llegada de archivo |
| Copia S3 → ADLS con `azcopy` cada 6 h | Lakeflow Connect o réplica gestionada |
| `ALL PRIVILEGES` a datos sobre todos los objetos | grants por esquema y tabla, con RLS y masking + Purview |
| Calidad en dos vías hacia `ops.dq_results` | framework de calidad con contratos versionados y cuarentena |
| Esquemas de bronze y silver abiertos | contrato congelado con evolución gobernada |
| Sin partición | liquid clustering medido por consulta |
| Checkpoints en un volumen | estado del pipeline gestionado por Lakeflow |

**Dependencias.**

| # | Entregable | De → para | Formato | Fecha | Mock |
| --- | --- | --- | --- | --- | --- |
| X1 (cambia) | + containers y external locations por esquema con nomenclatura fija, `stg-credential-adlsagentbankdev`, 4 roles al Access Connector, `ALL PRIVILEGES`, volumen UC, `CAN_USE` en `wh-agent` | Nicolle → Eladio, Manuela | Terraform `infra/databricks` | mié 30 | CSV local |
| X2 (cambia) | `bundles.yml` con `run_as = sp-pipelines` | Nicolle → Eladio | GitHub Actions | mié 30 (vencida desde mar 29) | `databricks bundle deploy` local |
| E1 (cambia) | esquema congelado de las 7 tablas gold; bronze y silver pasan a decisión abierta (E9) | Eladio → Manuela | `contracts/gold.yaml` v2 + tablas vacías | mié 30 | CSV 50 filas |
| E7 (cambia) | + depende de `ml.embeddings_endpoint` (abierta) y de lectura del scope `fh26` | Eladio → Manuela | Asset Bundle | jue 1 | 10 docs manuales |
| E8 (cambia) | `ops.dq_results` por dos vías + fixture de llegada tardía desde el manifiesto | Eladio → Nicolle | Delta | vie 2 | — |
| E9 (nueva) | contrato de columnas de bronze y silver tras inspeccionar `landing` | Eladio → Manuela | `contracts/gold.yaml` | jue 1 | esquemas abiertos |

**Base regulatoria.** No aplica en el hackathon. El dataset es de Factored y no sale del tenant: `landing` y los 6 esquemas quedan en `eastus2`. Las fuentes de `ref` son publicaciones públicas de reguladores, que entran por batch con URL y fecha de snapshot (ADR-12). Residencia y retención por país quedan en To-Be, a validar con legal.

El diagrama no cambia: la ingesta ya está dibujada en la página DEMO de `diagrams/arquitectura.drawio` como `data.ingest_s3` y `data.pipeline_medallon`.
