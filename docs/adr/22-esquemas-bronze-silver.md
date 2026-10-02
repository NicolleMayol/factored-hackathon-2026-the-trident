# 22-esquemas-bronze-silver

Owner: Eladio · v1 · 2026-10-01.

## ADR-22 · Contrato de bronze y silver (E9)  ·  rol: datos  ·  2026-10-01  ·  estado: cerrada

**Decisión.** Bronze recibe las 13 tablas del dataset 1:1 con el diccionario de datos más tres columnas de servicio; silver tipa, deduplica y normaliza solo las 7 tablas que alimentan `gold` y `ref`; las otras 6 se quedan en bronze.

Cierra la decisión abierta 1 de ADR-20. El contrato de columnas sale del **diccionario de datos de Factored** (LATAM Bank, versión 1.0.0, generado en septiembre de 2026), que es fuente primaria y no una inferencia. Lo que el diccionario no dice —la estructura de carpetas de `landing` y el reparto real de particiones— queda como verificación, no como decisión: un test compara el esquema inferido por `read_files()` contra este contrato y debe pasar antes de cerrar E1.

### El dataset
19.000.000 de filas, 13 tablas, México, Colombia y Argentina, del 2023-06-17 al 2026-06-17. Sintético, en español, con problemas de calidad deliberados: ~2 % de duplicados, ~5 % de nulos en campos opcionales, llegadas tardías y evolución de esquema.

### Bronze · las 13 tablas, 1:1
Sin reglas de negocio, sin tipado más allá de lo que trae el Parquet, sin dedup. Una tabla de streaming por fuente, poblada por Auto Loader (ADR-20).

| Tabla origen | Filas | Partición en origen | ¿Pasa a silver? | Por qué |
| --- | --- | --- | --- | --- |
| `customers` | 150.000 | `monthly_snapshot` | sí | `gold.customer_360` |
| `products` | 400.000 | `monthly_snapshot` | sí | `gold.customer_products` |
| `transactions` | 5.000.000 | `daily` | sí | `gold.customer_behavior_12m` |
| `call_center_interactions` | 800.000 | `daily` | sí | `gold.intent_labels`, `gold.contact_demand` |
| `call_transcripts` | 200.000 | `daily` | sí | `gold.intent_labels` |
| `satisfaction_surveys` | 250.000 | `daily` | sí | `gold.contact_demand` (CSAT) |
| `daily_exchange_rates` | 3.000 | `daily` | sí | conversión a USD |
| `branches` | 350 | `full_snapshot` | no | ninguna tabla gold del workflow 4 la usa |
| `service_agents` | 1.200 | `monthly_snapshot` | no | ídem |
| `marketing_campaigns` | 200 | `full_snapshot` | no | ídem |
| `digital_events` | 10.000.000 | `daily` | no | ídem; es la tabla más grande y no aporta al workflow 4 |
| `complaints` | 80.000 | `daily` | no | ídem |
| `campaign_sends` | 2.000.000 | `daily` | no | ídem |

Se ingieren las 13 aunque solo 7 sigan: bronze 1:1 es barato, deja evidencia de completitud frente al manifiesto de `data-landing` y evita reprocesar si el alcance cambia. Las 6 que no siguen no se transforman: `digital_events`, `campaign_sends` y `complaints` suman 12,08 M de filas y no alimentan ninguna tabla de `gold`.

### Columnas de servicio en bronze
| Columna | Tipo | Para qué |
| --- | --- | --- |
| `_ingested_at` | timestamp | frescura (`ops.dq_results.freshness_h`); se propaga a gold, donde ya está en `contracts/gold.yaml` |
| `_source_file` | string | trazar cada fila a su archivo; cruce contra `new` y `changed` del manifiesto |
| `_rescued_data` | string | columna nueva en origen que no estaba en el esquema; evolución sin romper la corrida (ADR-20) |

### Silver · las 7 tablas que siguen
Tipado según el diccionario, dedup, normalización. Sin agregación: eso es gold.

| Tabla | Dedup | Normalización | Grano resultante |
| --- | --- | --- | --- |
| `customers` | `document_number`, último `last_updated` | `country` a `Mexico\|Colombia\|Argentina`; `detected_accent` y `segment` en minúscula | 1 fila por `customer_id` |
| `products` | `product_id`, último `last_updated` | `currency` a `MXN\|COP\|ARS\|USD`; `days_past_due` nulo a 0 solo en silver, documentado | 1 fila por `product_id` |
| `transactions` | `transaction_id` | `amount_usd` nulo se completa con `daily_exchange_rates` por `transaction_date` y `currency` | 1 fila por `transaction_id` |
| `call_center_interactions` | `interaction_id` | `reason_category` a catálogo cerrado; `was_resolved` nulo queda nulo | 1 fila por `interaction_id` |
| `call_transcripts` | `transcript_id` | `detected_language` a ISO 639-1 | 1 fila por `transcript_id` |
| `satisfaction_surveys` | `survey_id` | `main_score` separado por `survey_type` (CSAT 1–5, NPS 0–10) | 1 fila por `survey_id` |
| `daily_exchange_rates` | `date`, `source_currency`, `target_currency` | — | 1 fila por la terna |

Reglas transversales: los nulos **no se imputan** salvo donde la tabla lo dice; se cuentan y se registran en `ops.dq_results`. Las filas huérfanas (el diccionario admite un porcentaje pequeño) no se descartan en silver: se marcan y se cuentan, y gold decide. Ninguna columna se renombra: el nombre del diccionario es el nombre en bronze y en silver.

### Leakage y columnas prohibidas
`customers` trae `gender`, `marital_status` y `date_of_birth`. Están en bronze y en silver porque bronze es 1:1 y silver no inventa recortes, pero **no pasan a `gold.customer_360`**: ya están declaradas en `excluded_from_features` de `contracts/gold.yaml`. El corte de `gold.customer_behavior_12m` sigue en 2025-06-30 y el split de `gold.intent_labels` sigue siendo temporal por `process_date`.

### Clientes de prueba
ADR-21 (M3) pide 5 clientes `TEST-*` en `gold.customer_360`. No vienen del dataset: se inyectan en **gold**, nunca en bronze ni en silver, y se reconocen por el prefijo `TEST-` en `customer_id`. Quedan fuera de toda agregación (`gold.contact_demand`, `gold.customer_behavior_12m`) y de cualquier métrica, para no contaminar los conteos con filas que no existen en el origen.

### Hallazgos del diccionario
**1 · El dataset no tiene portugués.** El diccionario es explícito: *"All text data is in Spanish with regional variations"*, y los países son México, Colombia y Argentina, sin Brasil. `gold.intent_labels` sale de `call_transcripts`, así que el clasificador de intención y acción (ADR-07) solo puede entrenarse y medirse en español. Choca con la regla que ADR-21 documentó —*"macro-F1 y AUC solo sobre el dataset de Factored"*— porque no hay dato de Factored en portugués con el que calcular macro-F1 en PT. No afecta al RAG ni al nodo Respond ni a `eval/cases.jsonl`: esos se apoyan en corpus sintético ES+PT, que sí es bilingüe. Es una decisión de ia-ml; la registro y aviso.

**2 · Deriva de contrato en `ref.regulator_rates`.** `data/mock/regulator_rates.csv` tiene una columna `rate_kind` que no existe en `contracts/gold.yaml`. O el contrato está incompleto o la columna sobra. Se resuelve con un test que compare las cabeceras de `data/mock/*.csv` contra `contracts/gold.yaml` en las dos direcciones, para que la deriva no vuelva a pasar inadvertida.

| Alternativas descartadas | Por qué |
| --- | --- |
| Llevar las 13 tablas a silver | `digital_events`, `campaign_sends` y `complaints` suman 12,08 M de filas y no alimentan ninguna tabla de gold |
| Ingerir en bronze solo las 7 que siguen | bronze 1:1 es barato y deja evidencia de completitud frente al manifiesto |
| Renombrar columnas en bronze o silver | rompe la trazabilidad contra el diccionario, que es la fuente primaria |
| Imputar los ~5 % de nulos en silver | esconde el problema de calidad que el reto plantea a propósito; se cuenta y se registra |
| Descartar las filas huérfanas en silver | el diccionario las documenta como deliberadas; se marcan y gold decide |
| Excluir `gender`, `marital_status` y `date_of_birth` desde bronze | bronze es copia fiel; el recorte es una regla de negocio y vive en gold |
| Inyectar los clientes `TEST-*` en bronze | contamina conteos y frescura con filas que no existen en el origen |
| Congelar el contrato solo tras consultar `landing` | el diccionario es fuente primaria de Factored; la consulta queda como verificación con test, no como bloqueo |

**Impacto.**

| Elemento | Estado | Owner | Consumers afectados | Qué deben hacer | Fecha límite |
| --- | --- | --- | --- | --- | --- |
| `data.bronze` | nuevo: 13 tablas 1:1 + `_ingested_at`, `_source_file`, `_rescued_data` | datos | — | nada | — |
| `data.silver` | nuevo: 7 tablas tipadas, deduplicadas y normalizadas | datos | ia-ml | Manuela: nada; gold no cambia de contrato | — |
| `data.pipeline_medallon` | cambia: alcance explícito, 13 en bronze y 7 en silver | datos | ia-ml | nada | — |
| `gold.intent_labels` | cambia: `detected_language` será español en la práctica; sin PT real | datos | **ia-ml** | Manuela: decidir cómo se reporta el clasificador en PT (ver aviso) | vie 2 |
| `ref.regulator_rates` | cambia: deriva de `rate_kind` entre `data/mock` y `contracts/gold.yaml` | datos | **ia-ml** | Manuela: confirmar si `rate_kind` se queda; si sí, entra al contrato con E6 | vie 2 |
| `gold.customer_360` | cambia: + 5 filas `TEST-*` inyectadas en gold, fuera de agregaciones | datos | ia-ml, servicio | Manuela y Nicolle: los `customer_id` de `docs/test-users.md` deben usar el prefijo `TEST-` | jue 1 |
| `contracts/gold.yaml` v2 → v3 | cambia: el bloque `source` apunta a ADR-22 en vez de dejar bronze y silver abiertos | datos | ia-ml | Manuela: ninguna acción | — |
| `gold.*` (7 tablas) | existe, sin cambio de esquema | datos | ia-ml | nada | — |

**Cómo se prueba.**

| Prueba | Umbral | Dónde se registra |
| --- | --- | --- |
| Esquema inferido por `read_files()` vs este contrato, por tabla | 0 diferencias de nombre o tipo; toda columna extra aparece en `_rescued_data` | test del bundle, antes de cerrar E1 |
| Las 13 tablas llegan a bronze | 13 de 13; conteo de archivos = manifiesto de `data-landing` | `ops.dq_results` |
| Dedup de silver | 0 duplicados por la llave declarada en cada tabla | `ops.dq_results` |
| Nulos | se cuentan, no se imputan; se reporta la tasa por columna | `ops.dq_results` |
| Columnas prohibidas | 0 apariciones de `gender`, `marital_status`, `date_of_birth` en `gold.*` | CI |
| Clientes de prueba | 5 filas con prefijo `TEST-` en `gold.customer_360`; 0 en bronze, silver y agregaciones | `ops.dq_results` |
| Cabeceras de `data/mock/*.csv` vs `contracts/gold.yaml` | 0 diferencias en ambas direcciones | CI (pytest) |
| Idioma real de `call_transcripts` | se reporta la distribución de `detected_language` | notebook de insights (E10) |

**Hackathon vs To-Be.**

| Hackathon | To-Be |
| --- | --- |
| 13 tablas en bronze, 7 en silver | silver completo si el alcance pasa del workflow 4 |
| Contrato de columnas del diccionario, verificado con test | contratos versionados con evolución gobernada y cuarentena |
| Nulos y huérfanos contados en `ops.dq_results` | cuarentena por fila con reproceso selectivo |
| Clientes `TEST-*` inyectados en gold | entorno de pruebas separado del de datos |
| Sin partición | liquid clustering medido por consulta |

**Dependencias.**

| # | Entregable | De → para | Formato | Fecha | Mock |
| --- | --- | --- | --- | --- | --- |
| E9 (cierra) | contrato de columnas de bronze y silver | Eladio → Manuela | este ADR + `contracts/gold.yaml` v3 | jue 1 | esquemas abiertos |
| E1 (cambia) | + verificación del esquema contra `landing` antes de cerrar; + 5 filas `TEST-*` en `gold.customer_360` | Eladio → Manuela | `contracts/gold.yaml` v3 + tablas | jue 1 | CSV 50 filas |
| E3 (cambia) | `gold.intent_labels` sin portugués real; el split temporal no cambia | Eladio → Manuela | Delta | vie 2 | 300 filas manuales |
| E6 (cambia) | + columna "Por qué" por fuente (ADR-21) y decisión sobre `rate_kind` | Eladio → Manuela | Delta + volumen `hackathon.ref.fuentes` | vie 2 | rangos aproximados |

**Base regulatoria.** No aplica. El dataset es sintético y de Factored, y no sale del tenant: bronze, silver y gold quedan en `eastus2`. `gender`, `marital_status` y `date_of_birth` existen en el origen y quedan fuera de las features por ADR-05, no por una norma concreta. Residencia y retención por país siguen en To-Be, a validar con legal.
