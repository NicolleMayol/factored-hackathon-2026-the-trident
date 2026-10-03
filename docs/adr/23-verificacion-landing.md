# 23-verificacion-landing

Owner: Eladio · v1 · 2026-10-02.

## ADR-23 · Verificación de `landing`: el origen es CSV  ·  rol: datos  ·  2026-10-02  ·  estado: cerrada

**Decisión.** La ingesta lee **CSV con `header` y `multiLine`, y hints de tipo explícitos por tabla**, desde dos rutas distintas: 6 archivos sueltos en la raíz y 7 carpetas particionadas estilo Hive. Corrige ADR-20 y ADR-22, que suponían Parquet.

Es la verificación que ADR-22 dejó como condición antes de cerrar E1. Se corrió el 2026-10-02 contra `landing` con `wh-agent`, leyendo con `read_files()`. Lo que sigue no es inferencia del diccionario: es lo que devolvió el almacenamiento.

### Qué se midió

| Hecho | Medido | Lo que decía el contrato |
| --- | --- | --- |
| Formato | **CSV en los 7.671 archivos**; cero Parquet | `format: parquet` en `gold.yaml`; "autodescriptivo, sin schema hints" en ADR-20 |
| Disposición | 6 CSV en la raíz (5 dimensiones + `daily_exchange_rates`) y 7 carpetas `<tabla>/year=YYYY/month=MM/day=DD/` | una sola ruta |
| Volumen | 7.671 archivos, 5,1 GB; cuadra con el manifiesto de `data-landing` | 7.671 archivos, 5.349.322.481 bytes |
| Reparto | `digital_events` pesa 3.583 MB: el 70 % del dataset | — |
| Nombres de columna | coinciden uno a uno con el diccionario en las 13 tablas | el diccionario es fuente primaria (ADR-22) |
| Tipos inferidos | **no** son los del contrato | `credit_score: int`, `days_past_due: int`, `decimal(n,2)` |

### `multiLine` no es una opción, es un requisito
Los campos de texto en español (`full_text`, `customer_text`, `agent_text`) y el JSON de `mentioned_entities` traen comas y saltos de línea entre comillas. Sin `multiLine`, el lector parte las filas y corre las columnas:

| Lectura de `call_transcripts/` | Filas | `transcript_id` distintos |
| --- | --- | --- |
| sin `multiLine` | 548.336 | 171.332 |
| con `multiLine` | **171.321** | **171.321** |

Sin la opción, `detected_language` queda con fragmentos como `{"account_numbers": 2`. **El pipeline no falla: entrega basura en silencio.** Por eso la prueba de conteo contra el diccionario es obligatoria por tabla, no opcional.

### Tipos: la inferencia no basta
| Columna | Inferido | Contrato |
| --- | --- | --- |
| `customers.credit_score` | `DOUBLE` | `int` |
| `customers.estimated_monthly_income` | `DOUBLE` | `decimal(12,2)` |
| `products.days_past_due` | `DOUBLE` | `int` |
| `products.current_balance`, `credit_limit` | `DOUBLE` | `decimal(15,2)` |
| `transactions.response_code` | `INT` | `VARCHAR(10)` en el diccionario |
| `call_transcripts.duration_seconds` | `STRING` | `INTEGER` en el diccionario |

El último es señal de calidad, no de tipado: hay valores no numéricos dentro. Se castea en silver y se cuenta el descarte en `ops.dq_results`.

### Perfil de `customers` (150.000 filas)
| Medición | Valor | Consecuencia |
| --- | --- | --- |
| `customer_id` distintos | 150.000 | sin duplicados |
| `document_number` distintos | 150.000 | la regla de dedup de ADR-22 **hoy no quita nada**; se queda como defensa |
| `_rescued_data` no nulo | 0 filas | sin deriva de esquema en el origen |
| `country` | `Argentina`, `Colombia`, **`México`** | con tilde; `gold.yaml` declara `Mexico`. Lo normaliza silver |
| `customer_status` | Active, Closed, Inactive, Suspended | coincide con P07 de `policy.yaml` |
| `segment` | Basic, Plus, Premium, Student | — |
| `detected_accent` | argentine, colombian, mexican | — |
| `credit_score` | 422–850 | dentro del rango `[300, 850]` del contrato |
| **nulos `credit_score`** | **14,99 %** | el diccionario promete ~5 % |
| **nulos `estimated_monthly_income`** | **20,02 %** | el diccionario promete ~5 % |

### Idioma: cero portugués, confirmado con dato
`call_transcripts.detected_language` es `es` en el **100 %** de las 171.321 filas. Confirma el hallazgo 1 de ADR-22, que hasta ahora se apoyaba solo en el texto del diccionario, y respalda la decisión de ia-ml en el PR #23: macro-F1 y AUC solo en ES sobre el held-out de Factored, PT como *slice* sintético fuera de la métrica principal.

| Alternativas descartadas | Por qué |
| --- | --- |
| Mantener `format: parquet` | medido: no hay un solo archivo Parquet |
| Leer sin `multiLine` y limpiar después | las filas ya vienen partidas y las columnas corridas; no hay nada que limpiar aguas abajo |
| Confiar en la inferencia de tipos | no da los tipos del contrato en 6 columnas, y `duration_seconds` saldría como texto |
| Una sola ruta de Auto Loader | la raíz y los particionados tienen disposición distinta; `year`/`month`/`day` solo existen en los hechos |
| Auto Loader también para las 6 de la raíz | exige un directorio y son archivos sueltos: `CloudInvalidPathException`. Y son snapshots, no flujos: van en lote |
| El shim `dlt` en vez de `pyspark.pipelines` | ADR-20 declara Spark Declarative Pipelines; `dlt` funciona por compatibilidad, pero no es la API del ADR |
| Quitar la dedup de `customers` | hoy no quita filas, pero el diccionario declara ~2 % de duplicados y el origen puede recargarse |
| Normalizar `México` a `Mexico` en bronze | bronze es copia fiel; la normalización es de silver (ADR-22) |

**Impacto.**

| Elemento | Estado | Owner | Consumers afectados | Qué deben hacer | Fecha límite |
| --- | --- | --- | --- | --- | --- |
| `data.ingest_s3` | cambia: `csv` con `header` y `multiLine`, hints por tabla, dos rutas | datos | — | nada | — |
| `data.bronze` | cambia: el tipado sale de hints, no del formato | datos | — | nada | — |
| `contracts/gold.yaml` v3 → v4 | cambia: `source.landing.format` de `parquet` a `csv`; + `format_opts` y `layout` | datos | ia-ml | Manuela: ninguna acción; las columnas de gold no cambian | — |
| ADR-20 (`08-datos.md`) | cambia: tabla de ingesta corregida | datos | ia-ml, servicio | nada | — |
| ADR-22 (`22-esquemas-bronze-silver.md`) | cambia: tabla de bronze con formato y rutas reales | datos | ia-ml | nada | — |
| `gold.customer_360` | cambia: nulos reales de `credit_score` 14,99 % y de `estimated_monthly_income` 20,02 % | datos | **ia-ml** | Manuela: el pre-score LightGBM (ADR-06) toma esas dos como features; decidir imputación o manejo de nulos, y si el baseline de regla sobre `credit_score` sigue siendo comparable con 15 % de ausencia | vie 2 |
| `gold.intent_labels` | existe: confirmado 100 % `es` | datos | ia-ml | nada; la decisión de PT del PR #23 queda respaldada con dato | — |

**Cómo se prueba.**

| Prueba | Umbral | Dónde se registra |
| --- | --- | --- |
| Conteo por tabla tras la ingesta vs lectura con `multiLine` | igual; cualquier exceso delata parseo partido | `ops.dq_results` |
| `transcript_id` distintos = filas en `call_transcripts` | 1:1 | `ops.dq_results` |
| Tipos de bronze vs hints declarados | 0 diferencias | test del bundle |
| `_rescued_data` no nulo | se cuenta y se reporta; no corta | `ops.dq_results` |
| Nulos por columna en `customer_360` | se reportan; sin umbral de corte | `ops.dq_results` |
| `country` normalizado en silver | 0 filas con `México` en `gold.customer_360` | `ops.dq_results` |
| Idioma de `gold.intent_labels` | se reporta la distribución | notebook de insights (E10) |

**Hackathon vs To-Be.**

| Hackathon | To-Be |
| --- | --- |
| Hints de tipo por tabla en el código del pipeline | contrato de esquema versionado y validado en el origen |
| `multiLine` sobre CSV | formato columnar en el origen, sin ambigüedad de parseo |
| Nulos contados y reportados | cuarentena por fila con reproceso selectivo |
| Verificación manual contra `landing` | test en CI que corre en cada cambio de contrato |

**Dependencias.**

| # | Entregable | De → para | Formato | Fecha | Mock |
| --- | --- | --- | --- | --- | --- |
| E9 (cierra del todo) | verificación contra `landing` ejecutada; contrato corregido | Eladio → Manuela | este ADR + `contracts/gold.yaml` v4 | hecho jue 2 | — |
| E1 (cambia) | sin bloqueo de verificación: ya está hecha | Eladio → Manuela | `contracts/gold.yaml` v4 + tablas | vie 2 | CSV 50 filas |
| E2 (cambia) | `customer_360` con 15 % de `credit_score` nulo y 20 % de ingreso nulo; se entrega el perfil de nulos junto a la tabla | Eladio → Manuela | Delta | vie 2 | CSV |

**Base regulatoria.** No aplica. El dataset es sintético y de Factored, y no sale del tenant: la verificación se corrió con `wh-agent` dentro del workspace, sin descargar nada.
