# 21-ajustes-ia-ml

Owner: Manuela · v1.5 · 2026-10-05 (cierre: adaptadores reales SQL/trazas/pre-score/embeddings/Cosmos, clasificador baseline y M5) · v1.4 · 2026-10-02 (ADR-24: corpus para los 6 tipos, puente `product_type_dataset`, montos de los casos desde el catálogo, E08 con plazo) · v1.3 · 2026-10-02 (it. 3: credenciales por perfil OAuth, `main` = llama-3.3-70b, guardrail determinista antes del LLM, decisiones pedidas en ADR-22) · v1.2 · 2026-10-02 (revisión del PR #18: `text_es`/`text_pt` para full-text en Cosmos; fuente de verdad del corpus repo → volumen; held-out desde `gold.intent_labels`) · v1.1 · 2026-10-01 (revisión de servicio en el PR #16: tolerancia al frío y costo del keep-warm; /healthz con estados; usuario `cliente_co_pt`; Eladio consumer de los usuarios de prueba).

## ADR-21 · Ajustes de ia-ml tras ADR-19 y ADR-20  ·  rol: ia-ml  ·  2026-10-01  ·  estado: cerrada

**Decisión.** ia-ml se alinea a la infraestructura desplegada (ADR-19) y a la plataforma de datos (ADR-20) con cinco cambios: el embedding bge-m3 se sirve desde un endpoint de Model Serving `embed-bge-m3` que usan el job E7 y el nodo Act; el scope de agente humano se llama `handoff:read`; la validación del JWT HS256 y las rutas `/chat/confirm` y `/healthz` pasan al código del agente; Jev queda en To-Be (cierra ADR-14); y las fuentes externas quedan justificadas una por una y excluidas de entrenamiento y evaluación, según la regla acordada con Factored.

### 1 · Embeddings: `embed-bge-m3` en Model Serving (cierra `ml.embeddings_endpoint`)

| Punto | Valor |
| --- | --- |
| Modelo | `hackathon.ml.bge_m3`, bge-m3 int8 ONNX, 1024 dims, lo registra ia-ml |
| Endpoint | `embed-bge-m3`, CPU small, scale-to-zero (false en ventana de evaluación), lo crea servicio en `infra/databricks` como `prescore-lgbm` |
| Consumidores | job E7 de datos (chunks) y nodo Act del agente (consulta) |
| Por qué no en la Function App | arranque ≤ 30 s (`infra.function_app`); el modelo int8 pesa ~570 MB y no cabe en ese presupuesto de arranque |
| Por qué no FM APIs | `databricks-bge-large-en` y `databricks-gte-large-en` son solo inglés; el corpus es es+pt |
| Garantía | chunk y consulta usan el mismo artefacto y la misma versión; `model_version` se guarda en cada chunk y en `ops.agent_turns` |
| Go/no-go int8 | Recall@5 en PT con int8 ≥ Recall@5 fp32 − 0,02 sobre 20 preguntas; si no, se registra fp32 |

### 2 · Identidad y rutas en el código del agente

| Punto | Valor |
| --- | --- |
| Scope de agente humano | `handoff:read`: exigido en `GET /handoff/{case_id}` y `GET /trace/{trace_id}` (`api.yaml` v1.1) |
| Usuario de prueba | `analista` en `docs/test-users.md`, junto a los 5 clientes (M3) |
| Validación | firma HS256 con `JWT_SIGNING_KEY`, `exp`, `customer_id` solo del token; `auth_level=ANONYMOUS` (ADR-19 v3) |
| `POST /chat/confirm` | confirma una acción pendiente (`action_id`) que `evaluate_eligibility` dejó en `confirm`; la confirmación es un turno más del grafo, con `trace_id` nuevo y `conversation_id` igual |
| `GET /healthz` | público, sin JWT; devuelve `ok / cold / down` por dependencia (`llm`, `cosmos`, `prescore`, `embed`, `sql`) sin mensajes ni nombres internos; 503 solo si `llm` o `cosmos` están `down` (N8 revisa esos dos). `cold` no es fallo: es scale-to-zero o auto-stop |
| Arranque | `agent/` no carga modelos al importar; adaptadores por inyección, elegidos por `AGENT_*` (`infra.yaml` v7) |

### 2b · Frío: tolerar, no mantener caliente

Mantener `wh-agent` (2X-Small, ~4 DBU/h), `prescore-lgbm` y `embed-bge-m3` encendidos las 24 h durante la evaluación (6 al 15 de octubre) no cabe en el presupuesto. Regla: el ping a `/healthz` cada 5 min se usa solo en demos anunciadas (~2 h/día); el resto del tiempo el agente tolera el frío.

| Punto | Valor |
| --- | --- |
| Detección | Act lee el estado de `/healthz` (cacheado 60 s) antes de llamar una tool |
| Dependencia `cold` | timeout extendido a 25 s (límite de la Function), una sola vez por dependencia y `conversation_id`; mensaje intermedio al cliente ("estoy consultando") |
| Si aun así vence | `escalate_reason = timeout_tool`, se escala con contexto |
| Dependencia `ok` | timeout normal de `tools.yaml` (8 s) |
| Costo estimado 7 días (no cotización) | keep-warm en demos: ~14 h × ~5 DBU × 0,70 USD ≈ 50 USD; sin ping ≈ 0 USD; keep-warm 24 h descartado: ~168 h × 5 DBU × 0,70 ≈ 590 USD |

### 3 · Escalamientos con causa

`ops.agent_turns` v3 añade `escalate_reason` ∈ {`policy`, `scope`, `no_citation`, `timeout_tool`, `guardrail`, `none`}. Separa la abstención correcta (política, scope, sin cita) del escalamiento por infraestructura (timeout de Model Serving o SQL Warehouse en frío, ADR-19 "Capacidad y límites"). Sin esta columna la matriz de confusión de acción mezclaría ambas.

### 4 · Fuentes externas: regla acordada con Factored (2026-10-01)

Factored autorizó fuentes externas con dos condiciones: justificar explícitamente cada una y no usarlas para testing. Se cumple así:

| Condición | Cómo | Dónde |
| --- | --- | --- |
| Justificación por fuente | columna "Por qué" con lo que aporta que el dataset no tiene | `docs/adr/12-fuentes-externas.md` v2, `README.md` |
| Fuera de entrenamiento | ninguna columna de `ref.*` en `features` de `contracts/gold.yaml`; test en CI | `eval/test_external_guard.py` (M7) |
| Fuera de evaluación | macro-F1 y AUC solo sobre el dataset de Factored; `eval/cases.jsonl` solo con los clientes de prueba y el catálogo sintético; `ref.*` entra únicamente como contexto del RAG y techo del motor de reglas | `docs/adr/06-evaluacion.md`, `eval/metrics.md` |
| Trazabilidad | `source`, `url`, `snapshot_date`, `es_sintetico` por fila y por chunk; la respuesta cita la fuente | `contracts/gold.yaml`, `contracts/chunks.yaml` |

### 4b · Corpus y evaluación tras la revisión del PR #18

| Punto | Decisión |
| --- | --- |
| Full-text en Cosmos | `policy_chunks` lleva `text_es` y `text_pt` (uno con el texto, el otro `null`) para que cada path tenga su analizador; `text` sigue siendo el campo de cita. Query híbrida: RRF de `VectorDistance` y `FullTextScore` con filtro por `country`, `language`, `product_code` (`chunks.yaml` v2.1) |
| Fuente de verdad del corpus | `data/policy_docs/` en el repo. `bundle sync` no escribe en volúmenes, así que `bundles.yml` añade tras el deploy `databricks fs cp -r data/policy_docs/docs/ dbfs:/Volumes/hackathon/ref/policy_docs/ --overwrite` (y `catalog.yaml` a `ref/fuentes/`); E7 lee del volumen y parte en chunks importando `build_corpus.py`, así los `chunk_id` son idénticos. Idioma del full-text en portugués: `pt-BR` |
| Dev set vs held-out | Los 24 casos de retrieval y los 82 de acción son **dev set** (los escribió ia-ml; el stub se afinó sobre ellos). El **held-out** de ADR-10 son las transcripciones de `gold.intent_labels` con split temporal (últimos 3 meses a test, E3), con `expected_action` derivada de `action_label`; se corre una vez con prompts congelados (sáb 3) y ese es el número que se reporta |

### 4c · Decisiones de la iteración 3 (acceso real, ADR-22)

| Punto | Decisión |
| --- | --- |
| Credenciales Databricks | Un solo módulo `agent/adapters/dbx_auth.py`: `DATABRICKS_TOKEN` > `sp-agent-ro` (OAuth M2M, Azure) > perfil de la CLI (`databricks auth login --profile fh26`, local). Sin tokens personales en `.env` |
| Modelo principal | `databricks-claude-sonnet-5` no existe en el workspace (A3, it. 3; SKU trial). `main` = `databricks-meta-llama-3-3-70b-instruct`, `small` = `llama-3.1-8b`; se compara con `gpt-oss-120b` en `eval/compare_models.py` y se elige con el número (`eval/models.md`). Se revisa Claude al pasar a Premium; cambio = `FM_ENDPOINT_MAIN` |
| Guardrail en dos capas | Con el LLM real el IVR subió a 0,267 porque la detección de inyección dependía de Understand. Ahora `agent/guardrails.py` (regex es/pt/en, determinista) corre antes del modelo y, si dispara, no se llama al LLM; `guardrail_hits` del LLM es la segunda capa. Test: todos los adversariales del dev set disparan sin LLM |
| Sin portugués en el dataset (ADR-22) | macro-F1 y AUC del clasificador (ADR-07) se reportan solo en ES sobre el held-out de Factored, con la limitación declarada en ADR-06 y ADR-11. PT se reporta como slice sintético fuera de la métrica principal: matriz de acción y Recall@5 sobre `eval/cases.jsonl` y el corpus sintético. PT es idioma del cliente, no país; en runtime lo resuelve el LLM |
| Nulos reales (ADR-23) | `credit_score` 15 % y `estimated_monthly_income` 20 % ausentes en `customer_360`. Pre-score LightGBM sin imputar (NaN nativo) más `credit_score_missing` e `income_missing` como features; AUC sobre toda la población. Baseline de regla: score ausente → Revisión humana (E04), comparado en dos cortes (población completa con su tasa de abstención, y filas con score). Motor: ingreso ausente con monto pedido → Revisión humana (E12) |
| Catálogo real (ADR-24) | Corpus R1–R8 para los 6 tipos (36 docs, 288 chunks): el agente no ofrece lo que no puede citar (M10). `get_customer_products` traduce `product_type_dataset` → canónico en un solo sitio, como `country_code`. Los montos del dev set salen del catálogo (`{{amount:<tipo>:min|mid|max}}`, `eval/amounts.py`), no de cifras fijas. E08 calcula la cuota con el plazo y la tasa máxima del producto (misma fórmula que R4), no `monto/12`. Condición para el catálogo: `rate_max` ≤ tope del país (si no, E11 bloquea todo el país) |
| Clasificador de intención (ADR-07, M5) | `gold.intent_labels` no es entrenable (42 frases plantilla bajo las 6 categorías, PR #31). Baseline TF-IDF char 2–5 + LogReg entrenado con 109 frases sintéticas propias del workflow 4 (`ml/data/intents_train.jsonl`) y evaluado en los mensajes únicos de `eval/cases.jsonl`: macro-F1 0,92 (es 0,94 · pt 0,89); sus errores son los que el guardrail determinista resuelve antes del LLM. El LLM se mide en la misma tabla (`run_eval` guarda `intent`). `docs/labels.md` + `ml/label_phrases.py` etiquetan las 42 frases de forma reproducible (override manual > modelo ≥ 0,6 > `low_confidence`); datos propaga con `es_entrenable = false` |
| Adaptadores reales (cierre) | `sql_warehouse` (Statement API, parametrizado, caché 10 min en tasas y catálogo), `trace_mlflow` (`ops.agent_turns` por hilo, nunca bloquea), `prescore_serving` (endpoint `prescore-lgbm` del pyfunc `hackathon.ml.prescore_lgbm`: probabilidad, IC = ±ECE, SHAP top-3), `embed_serving` (`embed-bge-m3`, lotes de 32), `store_cosmos` (VectorDistance + FullTextScore por idioma; RRF en `search_policy`). `ml/serving.py` crea los endpoints con scale-to-zero; `ml/load_cosmos.py` carga los 288 chunks con el mismo vector que usa la consulta |
| Pre-score (ADR-06) | Target proxy declarado: sin mora > 30 días en 12 m. Features: `customer_360` + `behavior_12m` sin `max_days_past_due` ni `ref.*`, con `credit_score_missing` e `income_missing`; sin TEST-*. LightGBM (NaN nativo) vs logística con mediana; AUC, Brier, ECE y AUC por país en MLflow `/Shared/fh26/agente` |
| `rate_kind` (ADR-22) | Se queda en `ref.regulator_rates` y entra al contrato con E6: `values: [ea, tna, cat, cft, usura]`. Tope por país: CO `usura`, MX `cat`, AR `cft` (`engine.CAP_KIND`); antes el motor solo miraba `usura` |

### 5 · Jev / TypeSafe AI → To-Be (cierra ADR-14)

El parser con esquema JSON en Understand y la validación de `handoff.schema.json` cubren el tipado de salida que Jev daría. Añadir una librería a cuatro días de la entrega es riesgo sin métrica que lo justifique.

### 6 · Dimensiones del reto y entregables bloqueantes

La página del reto publica cinco dimensiones (Technical Judgment, AI Engineering, Data Engineering, Machine Learning, Data Analytics) y exige link desplegado, 4–6 slides y video ≤ 3 min con interacciones en es y pt. Data Analytics no tiene entregable propio: se cubre con un notebook de insights sobre el dataset (demanda de crédito por país e idioma, segmentos, por qué el workflow 4) y el tablero de la matriz de confusión como soporte a decisión. `ci.yml` y `deploy.yml` pasan a bloqueantes: sin link desplegado no hay entrega.

| Alternativas descartadas | Por qué |
| --- | --- |
| bge-m3 cargado en la Function App (lazy) | +10–20 s en el primer turno de cada instancia; con 10 instancias y scale-to-zero el cold start se multiplica; rompe el p95 de 8 s |
| Embedding dentro del job E7 y otro en la Function | dos artefactos, dos versiones; una desviación mínima entre ambos degrada Recall@5 sin que nadie lo vea |
| `databricks-bge-large-en` (FM APIs) | solo inglés |
| Scope `agent:handoff` | el resto de scopes usa `recurso:acción` (`customer:read`, `credit:simulate`); `handoff:read` sigue la convención |
| Copiar datos de cliente a Cosmos para evitar el cold start del SQL Warehouse (propuesta abierta de ADR-19) | duplica datos de cliente fuera de Unity Catalog; se tolera el frío con timeout extendido una vez por sesión (sección 2b) |
| Keep-warm 24 h con ping a `/healthz` | ~590 USD en 7 días; solo en demos anunciadas |
| Jev en el hackathon | sin métrica que lo justifique; parser con esquema ya cubre el tipado |

**Impacto.**

| Elemento | Estado | Owner | Consumers afectados | Qué deben hacer | Fecha límite |
| --- | --- | --- | --- | --- | --- |
| `ml.embeddings_endpoint` | cierra: `embed-bge-m3` en Model Serving, modelo `hackathon.ml.bge_m3` | ia-ml (modelo), servicio (endpoint) | datos, servicio | Nicolle: endpoint en `infra/databricks` (CPU small, scale-to-zero salvo ventana de evaluación), `CAN_QUERY` para `sp-agent-ro` y `sp-pipelines`. Eladio: E7 llama al endpoint para embeber, no embebe local | vie 2 |
| `infra.model_serving` | cambia: + `embed-bge-m3`; `EMBED_ENDPOINT` en App Settings | servicio | ia-ml, datos | Nicolle: crear y exponer `EMBED_ENDPOINT` | vie 2 |
| `infra.function_app_settings` (`infra.yaml` v7) | cambia: + `EMBED_ENDPOINT`, + `AGENT_LLM`, `AGENT_STORE`, `AGENT_SQL`, `AGENT_PRESCORE`, `AGENT_EMBED`, `AGENT_TRACE` (valores `mock` o `real`) | servicio | ia-ml | Nicolle: añadir en Terraform con valor `real`; local `.env.example` con `mock` | vie 2 |
| `api.GET_/handoff`, `api.GET_/trace` (`api.yaml` v1.1) | cambia: scope `handoff:read` | ia-ml | servicio | Nicolle: `POST /session` emite `handoff:read` para el usuario `analista`; la vista `/handoff` de la Static Web App envía el JWT | jue 1 |
| `api.POST_/chat` (`api.yaml` v1.1) | cambia: `/chat/confirm` y `/healthz` detallados; sin cambio de request/response de `/chat` | ia-ml | servicio | Nicolle: botón de confirmación en el chat llama `/chat/confirm`; smoke N8 usa `/healthz` | vie 2 |
| `ops.agent_turns` (`ops.yaml` v3) | cambia: + `escalate_reason` | ia-ml | servicio, datos | Nicolle: tablero AI/BI con escalamientos por causa (X3). Eladio: nada | vie 2 |
| `policy.test_users` | nuevo: `docs/test-users.md` (M3) con 5 clientes + `analista` | ia-ml | servicio, datos | Nicolle: cargar en `POST /session`. Eladio: 5 filas sintéticas `TEST-*` en `gold.customer_360` con E1 | jue 1 |
| `tools.limits` (`tools.yaml` v2) | cambia: + `cold_start` (timeout extendido una vez, keep-warm solo en demos) | ia-ml | servicio | Nicolle: nada en infra; el smoke N8 usa `/healthz` con estados | vie 2 |
| `infra.ci_cd` | cambia: `ci.yml` (pytest + `run_eval.py` + guard de fuentes externas) y `deploy.yml` pasan a bloqueantes de entrega | servicio | ia-ml | Nicolle: ambos workflows antes de Integración 2 | sáb 3 |
| `data.analytics_insights` | nuevo: notebook de insights sobre el dataset (E10) | datos | ia-ml, servicio | Eladio: E4 ampliado a demanda por país e idioma y segmentos; una figura por hallazgo | sáb 3 |
| `docs/adr/12-fuentes-externas.md` v2 | cambia: justificación por fuente y regla de uso | ia-ml | datos | Eladio: columna "Por qué" en la tabla de fuentes de ADR-20 cuando registre E6 | vie 2 |
| ADR-14 | cierra: Jev a To-Be | ia-ml | — | nada | — |

**Cómo se prueba.**

| Prueba | Umbral | Dónde se registra |
| --- | --- | --- |
| Mismo vector para chunk y consulta | cosine(embed_job(x), embed_agent(x)) ≥ 0,999 sobre 20 textos | `eval/test_embeddings.py`, CI |
| int8 vs fp32 en PT | Recall@5 int8 ≥ fp32 − 0,02 | MLflow, `eval/` |
| JWT inválido, expirado o sin scope | 401 / 403; `/handoff` sin `handoff:read` → 403 | pytest |
| `/healthz` en frío | 200 con `cold` en serving y sql; 503 solo con `llm` o `cosmos` `down`; sin nombres internos en el cuerpo | pytest + smoke N8 |
| Tolerancia al frío | primera consulta con `sql = cold` responde en ≤ 25 s sin escalar; la segunda ya en 8 s | eval, `ops.agent_turns.escalate_reason` |
| Arranque de la Function App | `import agent` < 2 s en frío; sin descarga de modelos | pytest + `ops.infra_requests.cold_start` |
| Guard de fuentes externas | 0 columnas de `ref.*` en `features`; 0 casos de eval con origen externo | CI |
| Escalamientos por causa | 100 % de `action = escalate` con `escalate_reason ≠ none` | `ops.agent_turns` |

**Hackathon vs To-Be.**

| Hackathon | To-Be |
| --- | --- |
| `embed-bge-m3` CPU small, scale-to-zero | provisioned throughput, GPU si el corpus crece |
| Scope `handoff:read` en JWT mock | rol de analista en Entra ID |
| Parser JSON con esquema | Jev / TypeSafe AI u outputs estructurados nativos |
| Guard de fuentes externas como test | linaje en Unity Catalog con etiqueta `external` y política de uso |

**Dependencias.**

| # | Entregable | De → para | Formato | Fecha | Mock |
| --- | --- | --- | --- | --- | --- |
| M3 (cambia) | `policy/policy.yaml` + `docs/test-users.md` (5 clientes + `analista`) | Manuela → Nicolle, Eladio | repo | jue 1 | — |
| M9 (nueva) | modelo `hackathon.ml.bge_m3` registrado en UC | Manuela → Nicolle | MLflow registry | jue 1 noche | fp32 local |
| N9 (nueva) | endpoint `embed-bge-m3` + `EMBED_ENDPOINT`; `AGENT_*` en App Settings | Nicolle → Manuela, Eladio | Terraform | vie 2 | embedding local en `AGENT_EMBED=mock` |
| N10 (nueva) | `ci.yml` y `deploy.yml` | Nicolle → todos | GitHub Actions | sáb 3 | `pytest` local |
| E10 (nueva) | notebook de insights (Data Analytics) | Eladio → Manuela, Nicolle | notebook + figuras | sáb 3 | — |
| E7 (cambia) | embebe con `embed-bge-m3` | Eladio → Manuela | Asset Bundle | vie 2 | 10 docs manuales |

**Base regulatoria.** Sin cambio respecto a ADR-05 y ADR-12: revisión humana obligatoria en banda cerrada; ninguna fuente externa en vivo; datos del cliente solo por `customer_id` del token. A validar con legal.
