# 08-datos

Owner: Eladio · v3 · 2026-10-01 (revisión de servicio en el PR #8; ADR-22 cierra la decisión abierta 1 en `22-esquemas-bronze-silver.md`).

## ADR-20 · Plataforma de datos e ingesta  ·  rol: datos  ·  2026-09-30  ·  estado: cerrada

**Decisión.** El medallón corre en Spark Declarative Pipelines sobre Unity Catalog, con un container y una external location por esquema, y la ingesta es Auto Loader con directory listing desde el contenedor `landing` (Parquet), con calidad en dos vías hacia `ops.dq_results`.

### Qué pide esta decisión a servicio
Datos no crea recursos (ADR-19). Esta es la lista completa de lo que hace falta para que exista el medallón.

| # | Recurso o permiso | Nombre | Para qué |
| --- | --- | --- | --- |
| 1 | Catálogo y esquemas en Unity Catalog | `hackathon` · `bronze`, `silver`, `gold`, `ref`, `ops`, `ml` | sin esto no hay dónde crear tablas |
| 2 | Containers en `adlsagentbankdev`, uno por esquema y con el mismo nombre | `bronze`, `silver`, `gold`, `ref`, `ops`, `ml` | managed location por esquema; frontera de permisos por capa |
| 3 | Storage credential | `stg-credential-adlsagentbankdev` | identidad de Unity Catalog sobre ADLS |
| 4 | External locations, una por container más `landing` | `ext-loc-adlsagentbankdev-{bronze,silver,gold,ref,ops,ml-data,landing}` (el container de `ml` es `ml-data`: Azure pide 3 a 63 caracteres; servicio agregó `unity-catalog` para el catálogo) | managed location de cada esquema y lectura del dataset |
| 5 | Grants por esquema, no globales | Eladio y `sp-pipelines`: `USE CATALOG hackathon` + `ALL PRIVILEGES` en `bronze`, `silver`, `gold`, `ref`, `ops`. `sp-pipelines` además: `READ FILES` en `ext-loc-adlsagentbankdev-landing` | trabajar sin pedir un grant por tabla, sin alcanzar `ml` (de ia-ml) |
| 6 | Volúmenes managed de Unity Catalog | `hackathon.ref.policy_docs` (ES+PT, E7) · `hackathon.ref.fuentes` (snapshots de `ref`, E6) | insumos que no van al repo |
| 7 | SQL Warehouse | `CAN_USE` en `wh-agent` para Eladio y `sp-pipelines` | validar tablas y correr los checks de calidad |
| 8 | Workflow de despliegue | `bundles.yml` con `run_as = sp-pipelines` (X2) | desplegar los Asset Bundles de `data/` |
| 9 | Lectura del secret scope `fh26` (`cosmos-key`) | `sp-pipelines` | E7 carga el JSONL de chunks a Cosmos |

Resuelto en la revisión del PR #8, ya no se pide: roles extra al Access Connector (se queda con `Storage Blob Data Contributor`, porque la ingesta va con directory listing) y volumen para checkpoints (los gestiona el pipeline).

Nicolle tiene account admin de Databricks desde el 2026-09-29, así que `infra/databricks` ya no está bloqueado por permisos. Las notas que dicen lo contrario en `infra/README.md` y `docs/adr/09-servicio.md` las corrige servicio en su PR; `contracts/infra.yaml` queda corregido en este.

### Ingesta
Fuente efectiva: `abfss://landing@adlsagentbankdev.dfs.core.windows.net/factored-datathon/data/`, que puebla el workflow `data-landing` con `azcopy` cada 6 h al minuto 17. Carga inicial del 2026-09-30: 7.671 archivos, 5.349.322.481 bytes, 0 fallas. Databricks no lee S3: Unity Catalog en Azure no toma llaves de S3 y serverless no deja ponerlas en la config de Spark (ADR-19).

| Parámetro | Valor | Por qué |
| --- | --- | --- |
| `cloudFiles.format` | `parquet` | formato del dataset; autodescriptivo, sin schema hints |
| Descubrimiento | directory listing | listar 7.671 archivos cada 6 h toma segundos; file events exige una cola y una suscripción de Event Grid que Databricks crea fuera de Terraform |
| Checkpoint y schema location | los gestiona el pipeline | con Auto Loader en SDP no se configuran a mano: un full refresh no limpia esos directorios |
| Evolución de esquema | `addNewColumns` + `_rescued_data` preservada en bronze | una columna nueva en origen no detiene la corrida y queda registrada |
| Horario | cada 6 h al minuto 50 | 33 min después de `data-landing` (:17), para leer la copia ya cerrada |
| Partición | ninguna | 5,35 GB no la justifica; liquid clustering si una tabla lo pide |

El procesamiento sigue siendo incremental: Auto Loader lleva su propio registro de archivos vistos, independiente del modo de descubrimiento.

Capas: `bronze` es 1:1 con el archivo origen más `_ingested_at`, `_rescued_data` y la ruta del archivo, sin reglas de negocio. `silver` tipa, deduplica (`document_number`, último `last_updated`) y normaliza país e idioma. `gold` y `ref` son las 7 tablas de `contracts/gold.yaml`, sin cambio de contrato. En `ops` solo escribo `ops.dq_results`: `ops.agent_turns` y `ops.ml_inference` son de ia-ml y `ops.infra_requests` de servicio.

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

Ninguna fuente se consulta en vivo (ADR-12). Ningún dato del dataset entra al repo: los snapshots de `ref` van a `hackathon.ref.fuentes` y los `policy_docs` a `hackathon.ref.policy_docs`.

### Decisiones abiertas
Ninguna. Las tres se cerraron:

| # | Qué | Cómo se cerró |
| --- | --- | --- |
| 1 | Contrato de columnas de bronze y silver | **ADR-22** (`22-esquemas-bronze-silver.md`): 13 tablas 1:1 en bronze, 7 en silver, columnas del diccionario de Factored v1.0.0 |
| 2 | `ml.embeddings_endpoint` | **ADR-21** (ia-ml): Model Serving `embed-bge-m3`, modelo `hackathon.ml.bge_m3`; E7 llama al endpoint y no embebe local |
| 3 | Cobertura del SKU `trial` | revisión del PR #8: serverless funciona (Premium + Unity Catalog + `eastus2`); la cobertura de DBU se mide con `system.billing.usage` en la primera corrida |

ADR-22 abre dos hallazgos del diccionario de datos, ambos de ia-ml: el dataset no tiene portugués y hay una deriva de `rate_kind` en `ref.regulator_rates`.

| Alternativas descartadas | Por qué |
| --- | --- |
| Jobs con notebooks PySpark para el medallón | sin linaje ni expectativas nativas; la calidad habría que construirla a mano |
| Auto Loader en file events | exige Storage Account Contributor sobre toda la cuenta y EventGrid EventSubscription Contributor sobre el resource group, registrar `Microsoft.EventGrid`, y una cola y una suscripción que Databricks crea fuera de Terraform; a 7.671 archivos el listado toma segundos y no lo justifica |
| Configurar checkpoint y schema location a mano | con Auto Loader en SDP los gestiona el pipeline; un full refresh no limpia esos directorios |
| Leer S3 directo desde Databricks serverless | Unity Catalog en Azure no toma llaves de S3 y serverless no deja ponerlas en la config de Spark (ADR-19) |
| Un solo container para los 6 esquemas | sin frontera de permisos por capa; el managed location por esquema la da sin trabajo extra |
| `ALL PRIVILEGES` sobre todos los objetos de Databricks | alcanza `ml` (de ia-ml) y las tablas de `ops` de otros roles; un permiso no debe depender de una convención |
| Fixture sintético de llegada tardía | el manifiesto de `data-landing` ya da evidencia real |
| Partición de bronze por fecha | 5,35 GB no la justifica |
| Congelar bronze y silver hoy | las columnas saldrían del diccionario de datos y no de los archivos |

**Impacto.**

| Elemento | Estado | Owner | Consumers afectados | Qué deben hacer | Fecha límite |
| --- | --- | --- | --- | --- | --- |
| `infra.adls` | cambia: +6 containers (`bronze`…`ml`), storage credential `stg-credential-adlsagentbankdev`; el Access Connector se queda con `Storage Blob Data Contributor` | servicio | datos, ia-ml | Nicolle: aplicar en `infra/databricks` | jue 1 |
| `infra.uc_external_locations` | nuevo: 7 × `ext-loc-adlsagentbankdev-{esquema\|landing}`; `READ FILES` de `sp-pipelines` sobre la de `landing` | servicio | datos, ia-ml | Nicolle: crear con esa nomenclatura; managed location por esquema | jue 1 |
| `infra.uc_volumes` | nuevo: `hackathon.ref.policy_docs` y `hackathon.ref.fuentes`, managed | servicio | datos, ia-ml | Nicolle: crear; la escritura sale de los grants de `ref` | jue 1 |
| `infra.databricks_access` | cambia: `USE CATALOG hackathon` + `ALL PRIVILEGES` en `bronze`, `silver`, `gold`, `ref`, `ops` para datos y `sp-pipelines`; `CAN_USE` en `wh-agent`; sin alcance sobre `ml` | servicio | datos, ia-ml | Nicolle: aplicar grants | jue 1 |
| `infra.key_vault` | cambia: lectura del scope `fh26` (`cosmos-key`) para `sp-pipelines` | servicio | datos, ia-ml | Nicolle: grant de lectura | jue 1 |
| `infra.ci_cd` | cambia: `bundles.yml` con `run_as = sp-pipelines` | servicio | datos, ia-ml | Nicolle: crear el workflow | jue 1 |
| `data.source_s3` | cambia: Databricks ya no lee S3; la fuente efectiva es `landing` | datos | — | nada | — |
| `data.ingest_s3` | cambia: Auto Loader en SDP desde `landing`, Parquet, directory listing | datos | — | nada | — |
| `data.pipeline_medallon` | cambia: SDP declarativo en las tres capas; DQ en dos vías | datos | ia-ml | Manuela: nada en código; el contrato de gold no cambia | — |
| `ops.dq_results` | cambia: se puebla desde expectativas de SDP y checks propios; esquema sin cambio | datos | servicio | Nicolle: la alerta `dq_failed = 1` sigue igual | vie 2 |
| `ml.embeddings_endpoint` | nuevo, **abierta**: bge-m3 de `chunks.yaml` no existe en `fm_apis` | a definir | datos, servicio | Manuela: decidir si va en Model Serving o dentro del job de E7 | jue 1 |
| `gold.*` (7 tablas) | existe, sin cambio de esquema | datos | ia-ml | nada | — |
| `contracts/gold.yaml` v1 → v2 | cambia: añade el bloque `source` (landing, Parquet, Auto Loader, horario) y la decisión abierta de bronze/silver | datos | ia-ml | Manuela: ninguna acción; las columnas de gold son las mismas | — |

**Cómo se prueba.**

| Prueba | Umbral | Dónde se registra |
| --- | --- | --- |
| Auto Loader procesa solo lo nuevo | archivos procesados = `new` + `changed` del manifiesto de `data-landing` | log del job + `ops.dq_results` |
| Expectativas de SDP en las tres capas | 0 violaciones duras | evento del pipeline → `ops.dq_results` |
| Frescura de gold | ≤ 24 h | `ops.dq_results.freshness_h`; alerta de `contracts/ops.yaml` |
| Grano y llave de las 7 tablas gold | 0 duplicados por llave | `ops.dq_results` |
| Leakage | 0 filas con `process_date` posterior al corte en train; 0 columnas prohibidas en features | `ops.dq_results` |
| Reproceso de un manifiesto con `new` no vacío | las filas nuevas entran sin duplicar las anteriores | E8 |
| `sp-pipelines` escribe en los 5 esquemas concedidos y **no** en `ml` | `CREATE TABLE` pasa en los 5; falla en `ml` | CI (test SQL) |
| Latencia del listado de `landing` | se reporta por corrida; si pasa de minutos, se reabre file events | log del job |
| Costo y cobertura de DBU del SKU `trial` | se mide a diario | `system.billing.usage` |

**Hackathon vs To-Be.**

| Hackathon | To-Be |
| --- | --- |
| SDP cada 6 h por horario | Lakeflow con trigger por llegada de archivo |
| Auto Loader con directory listing | file events, con la cola y la suscripción de Event Grid gestionadas desde IaC |
| Copia S3 → ADLS con `azcopy` cada 6 h | Lakeflow Connect o réplica gestionada |
| `ALL PRIVILEGES` por esquema | grants por tabla, con RLS y masking + Purview |
| Calidad en dos vías hacia `ops.dq_results` | framework de calidad con contratos versionados y cuarentena |
| Esquemas de bronze y silver abiertos | contrato congelado con evolución gobernada |
| Sin partición | liquid clustering medido por consulta |

**Dependencias.**

| # | Entregable | De → para | Formato | Fecha | Mock |
| --- | --- | --- | --- | --- | --- |
| X1 (cambia) | + containers y external locations por esquema con nomenclatura fija, `stg-credential-adlsagentbankdev`, grants por esquema para Eladio y `sp-pipelines`, `READ FILES` en la external location de `landing`, volúmenes `hackathon.ref.policy_docs` y `hackathon.ref.fuentes`, `CAN_USE` en `wh-agent` | Nicolle → Eladio, Manuela | Terraform `infra/databricks` | jue 1 | CSV local |
| X2 (cambia) | `bundles.yml` con `run_as = sp-pipelines` | Nicolle → Eladio | GitHub Actions | jue 1 (vencida desde mar 29) | `databricks bundle deploy` local |
| E1 (cambia) | esquema congelado de las 7 tablas gold; bronze y silver pasan a decisión abierta (E9); + 5 filas sintéticas `TEST-*` en `gold.customer_360` (ADR-21) | Eladio → Manuela | `contracts/gold.yaml` v2 + tablas vacías | jue 1 | CSV 50 filas |
| E7 (cambia) | + depende de `ml.embeddings_endpoint` (abierta) y de lectura del scope `fh26` | Eladio → Manuela | Asset Bundle | jue 1 | 10 docs manuales |
| E8 (cambia) | `ops.dq_results` por dos vías + fixture de llegada tardía desde el manifiesto | Eladio → Nicolle | Delta | vie 2 | — |
| E9 (nueva) | contrato de columnas de bronze y silver tras inspeccionar `landing` | Eladio → Manuela | `contracts/gold.yaml` | jue 1 | esquemas abiertos |

**Base regulatoria.** No aplica en el hackathon. El dataset es de Factored y no sale del tenant: `landing` y los 6 esquemas quedan en `eastus2`. Las fuentes de `ref` son publicaciones públicas de reguladores, que entran por batch con URL y fecha de snapshot (ADR-12). Residencia y retención por país quedan en To-Be, a validar con legal.

El diagrama no cambia: la ingesta ya está dibujada en la página DEMO de `diagrams/arquitectura.drawio` como `data.ingest_s3` y `data.pipeline_medallon`.
