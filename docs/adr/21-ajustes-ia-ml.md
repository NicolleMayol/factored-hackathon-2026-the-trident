# 21-ajustes-ia-ml

Owner: Manuela · v1 · 2026-10-01.

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
| `GET /healthz` | revisa LLM, Cosmos, Model Serving (`prescore-lgbm`, `embed-bge-m3`) y SQL Warehouse; 200 solo si los cuatro responden |
| Arranque | `agent/` no carga modelos al importar; adaptadores por inyección, elegidos por `AGENT_*` (`infra.yaml` v7) |

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
| Copiar datos de cliente a Cosmos para evitar el cold start del SQL Warehouse (propuesta abierta de ADR-19) | duplica datos de cliente fuera de Unity Catalog; un ping a `/healthz` cada 5 min en ventana de evaluación mantiene `wh-agent` caliente (auto-stop 10 min) |
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
| `policy.test_users` | nuevo: `docs/test-users.md` (M3) con 5 clientes + `analista` | ia-ml | servicio | Nicolle: cargar en `POST /session` | jue 1 |
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
