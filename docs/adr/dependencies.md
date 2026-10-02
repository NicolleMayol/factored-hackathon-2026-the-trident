# Dependencias entre roles · v6 · 2026-10-01 (ADR-22: E9 cierra; E1, E3, E6 cambian · ADR-19 v3.3: N3 cambia · ADR-21: M3, E7 cambian; M9, N9, N10, E10 nuevas · ADR-18: N2, X1, M6, X3 cambian; N8 nueva · ADR-19: X1 pasa a Nicolle; N1, N2, N3, N5, E1, E2 cambian · ADR-19 v3: N1, N5 · ADR-20: X1, X2, E1, E7, E8 cambian; E9 nueva)
Regla: cada entregable tiene dueño, receptor, formato y fecha; hasta que llega, el receptor trabaja con mock. Integraciones: mié 30 sep y sáb 3 oct.

## Manuela ← Eladio
| # | Entregable | Formato / acceso | Fecha | Mock |
| --- | --- | --- | --- | --- |
| E1 | Esquema congelado 7 tablas gold; bronze y silver cerrados en ADR-22; + 5 filas sintéticas TEST-* en gold.customer_360 (ADR-21 v1.1), solo en gold; + verificación del esquema inferido por read_files() contra ADR-22 antes de cerrar | contracts/gold.yaml v3 + tablas vacías hackathon.gold | Jue 1 (depende de X1) | CSV 50 filas |
| E2 | customer_360, customer_products, customer_behavior_12m (corte 2025-06-30) | Delta; wh-agent; sp-agent-ro | Mié 30 mediodía (depende de X1) | CSV |
| E3 | intent_labels con split temporal; sin portugués real: el dataset es solo español (ADR-22, hallazgo 1) | Delta | Vie 2 | 300 filas manuales |
| E4 | contact_demand + notebook "por qué workflow 4" | Delta | Jue 1 | — |
| E5 | credit_product_catalog sintético 3×5 | Delta + policy/catalog.yaml | Mar 29 noche | 5 productos inventados |
| E6 | ref.regulator_rates con fuente y fecha; + columna "Por qué" por fuente (ADR-21) y decisión sobre rate_kind (ADR-22, hallazgo 2) | Delta + volumen hackathon.ref.fuentes | Vie 2 | rangos aprox. |
| E7 | Pipeline policy_docs ES+PT → policy_chunks (+JSONL Cosmos); depende de ml.embeddings_endpoint (abierta) y de lectura del scope fh26 | Asset Bundle | Jue 1 | 10 docs manuales |
| E8 | ops.dq_results por dos vías (expectativas SDP + checks propios) + fixture de llegada tardía desde el manifiesto de data-landing | Delta | Vie 2 | — |
| E9 | Contrato de columnas de bronze y silver (cerrado en ADR-22: 13 tablas en bronze, 7 en silver, columnas del diccionario de Factored v1.0.0; verificación contra landing con test antes de cerrar E1) | docs/adr/22-esquemas-bronze-silver.md + contracts/gold.yaml v3 | hecho jue 1 | esquemas abiertos |

## Manuela ← Nicolle
| # | Entregable | Fecha | Mock |
| --- | --- | --- | --- |
| N1 | Repo en NicolleMayol/factored-hackathon-2026-the-trident; workflow infra (plan en PR, apply con aprobación); OIDC hecho; pytest, eval y gitleaks pendientes; solo Nicolle mergea | hecho mié 30 | rama local |
| N2 | Function App Flex Consumption 2048 MB + App Settings de contracts/infra.yaml v3 (+ APPLICATIONINSIGHTS_CONNECTION_STRING; secretos como referencias a Key Vault; credenciales de sp-agent-ro listas) | hecho mié 30 | func start + local.settings.json |
| N3 | Cosmos free tier: conversations, handoffs, policy_chunks (DiskANN + full-text `text_es` es-ES / `text_pt` pt-BR), 400 RU/s dedicados por contenedor | hecho mar 29; full-text jue 1 | emulador / LanceDB |
| N4 | Identidad mock POST /session + 5 clientes de prueba | Mar 29 | JWT local |
| N5 | Static Web Apps Free: chat + /handoff (ADR-19 v3; recurso creado) | Mié 30 | curl |
| N6 | App Insights + export ops.infra_requests | Jue 1 | logs locales |
| N9 | endpoint Model Serving embed-bge-m3 + EMBED_ENDPOINT; App Settings AGENT_* (ADR-21) | Vie 2 | AGENT_EMBED=mock (embedding local) |
| N10 | ci.yml (pytest + run_eval.py + guard de fuentes externas) y deploy.yml; bloqueantes de entrega | Sáb 3 | pytest local |
| N7 | Carga 10/25/50 usuarios; p50/p95; costo por caso | Sáb 3 | — |
| N8 | Job CI post-deploy: smoke /chat con subconjunto de eval/cases.jsonl; p95 en caliente separado de cold start | Vie 2 | func start local |

## Eladio y Nicolle ← Manuela
| # | Entregable | Para | Fecha |
| --- | --- | --- | --- |
| M1 | contracts/tools.yaml | Eladio, Nicolle | Lun 28 noche |
| M2 | contracts/api.yaml + handoff.schema.json | Nicolle | Lun 28 noche |
| M3 | policy/policy.yaml + docs/test-users.md (5 clientes + analista con handoff:read) | Nicolle, Eladio | hecho jue 1 (ADR-21) |
| M4 | contracts/chunks.yaml | Eladio, Nicolle | Mar 29 |
| M5 | docs/labels.md | Eladio | Mar 29 |
| M6 | módulo /agent handle(message, session): grafo LangGraph compilado, sin databricks-agents, prompts en agent/prompts/ con hash + tests | Nicolle | Mié 30 |
| M7 | eval/metrics.md + eval/cases.jsonl | Nicolle | Vie 2 |
| M8 | contracts/ops.yaml v3 (+ escalate_reason) | Eladio, Nicolle | hecho jue 1 |
| M9 | modelo hackathon.ml.bge_m3 (bge-m3 int8 ONNX) registrado en UC | Nicolle | Jue 1 noche |

## Eladio ↔ Nicolle
| # | Entregable | De → para | Fecha |
| --- | --- | --- | --- |
| X1 | Workspace Premium trial, ADLS + Access Connector, Key Vault + secret scope fh26 (cosmos-key; las llaves de S3 solo viven en GitHub), storage credential, catálogo hackathon y esquemas bronze/silver/gold/ref/ops/ml, grants del equipo, sp-agent-ro, sp-pipelines, wh-agent con CAN_USE, experimento /Shared/fh26/agente con CAN_EDIT; y por ADR-20: un container por esquema con el mismo nombre, stg-credential-adlsagentbankdev, 8 external locations ext-loc-adlsagentbankdev-{bronze,silver,gold,ref,ops,ml-data,landing,unity-catalog}, grants por esquema (ALL PRIVILEGES en bronze/silver/gold/ref/ops, sin ml) para Eladio y sp-pipelines, READ FILES de sp-pipelines en la external location de landing, volúmenes managed hackathon.ref.policy_docs y hackathon.ref.fuentes, lectura del scope fh26 para sp-pipelines; todo en Terraform (ADR-19) (mock: CSV local; experimento personal de Manuela) | Nicolle → Eladio, Manuela | hecho mié 30 (22:00) |
| X2 | Asset Bundles desde GitHub Actions: bundles.yml con run_as = sp-pipelines | Nicolle → Eladio | hecho mié 30 (noche) |
| X3 | Export App Insights → ops.infra_requests; tablero AI/BI con p95 en caliente, cold start por separado y escalamientos por escalate_reason | Nicolle → Eladio | Vie 2 |

## Calendario
| Día | Eladio | Manuela | Nicolle | Sync |
| --- | --- | --- | --- | --- |
| Lun 28 | — | M1, M2, esqueleto | — | 21:00 contratos firmados |
| Mar 29 | E5, E6, E7 inicio | M3–M5, corpus, reglas | X1 (workspace), N2, N3, N4, X2 | — |
| Mié 30 | E1, E2, E3, E7 | M6, caso normal | X1 (grants), N1, N2, N5 | Integración 1 |
| Jue 1 | E4, E9 | ADR-21, M3, M8, M9, modelos + baselines | N6, N9 inicio | — |
| Vie 2 | E7 (con embed-bge-m3), E8 | ambiguo/escalamiento, PT, guardrails, eval, M7 | N9, X3, N8 | — |
| Sáb 3 | README datos, E10 insights | harness, métricas | N10, N7 | Integración 2 |
| Dom 4 | slides datos | README, slides arq. | video, setup | ensayo ×2 |
| Lun 5 | entrega | entrega | entrega | — |
