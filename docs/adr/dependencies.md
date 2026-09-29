# Dependencias entre roles · v2 · 2026-09-29 (ADR-18: N2, X1, M6, X3 cambian; N8 nueva)
Regla: cada entregable tiene dueño, receptor, formato y fecha; hasta que llega, el receptor trabaja con mock. Integraciones: mié 30 sep y sáb 3 oct.

## Manuela ← Eladio
| # | Entregable | Formato / acceso | Fecha | Mock |
| --- | --- | --- | --- | --- |
| E1 | Esquema congelado 7 tablas gold | contracts/gold.yaml + tablas vacías hackathon.gold | Lun 28 noche | CSV 50 filas |
| E2 | customer_360, customer_products, customer_behavior_12m (corte 2025-06-30) | Delta; wh-agent; sp-agent-ro | Mié 30 mediodía | CSV |
| E3 | intent_labels con split temporal | Delta | Mié 30 noche | 300 filas manuales |
| E4 | contact_demand + notebook "por qué workflow 4" | Delta | Jue 1 | — |
| E5 | credit_product_catalog sintético 3×5 | Delta + policy/catalog.yaml | Mar 29 noche | 5 productos inventados |
| E6 | ref.regulator_rates con fuente y fecha | Delta + data/ref/ | Mar 29 | rangos aprox. |
| E7 | Pipeline policy_docs ES+PT → policy_chunks (+JSONL Cosmos) | Asset Bundle | Mié 30 | 10 docs manuales |
| E8 | ops.dq_results + fixture llegada tardía | Delta | Vie 2 | — |

## Manuela ← Nicolle
| # | Entregable | Fecha | Mock |
| --- | --- | --- | --- |
| N1 | Repo, CI (pytest + eval + adr-impact), solo Nicolle mergea | Lun 28 noche | rama local |
| N2 | Function App Flex Consumption + App Settings de contracts/infra.yaml v2 (FM_ENDPOINT_MAIN, FM_ENDPOINT_SMALL, MLFLOW_TRACKING_URI, MLFLOW_EXPERIMENT) | Mié 30 mañana | func start + local.settings.json |
| N3 | Cosmos free tier: conversations, handoffs, policy_chunks (DiskANN) | Mar 29 | emulador / LanceDB |
| N4 | Identidad mock POST /session + 5 clientes de prueba | Mar 29 | JWT local |
| N5 | App Service F1 chat + /handoff | Mié 30 | curl |
| N6 | App Insights + export ops.infra_requests | Jue 1 | logs locales |
| N7 | Carga 10/25/50 usuarios; p50/p95; costo por caso | Sáb 3 | — |
| N8 | Job CI post-deploy: smoke /chat con subconjunto de eval/cases.jsonl; p95 en caliente separado de cold start | Vie 2 | func start local |

## Eladio y Nicolle ← Manuela
| # | Entregable | Para | Fecha |
| --- | --- | --- | --- |
| M1 | contracts/tools.yaml | Eladio, Nicolle | Lun 28 noche |
| M2 | contracts/api.yaml + handoff.schema.json | Nicolle | Lun 28 noche |
| M3 | policy/policy.yaml + 5 clientes de prueba | Nicolle, Eladio | Mar 29 |
| M4 | contracts/chunks.yaml | Eladio, Nicolle | Mar 29 |
| M5 | docs/labels.md | Eladio | Mar 29 |
| M6 | módulo /agent handle(message, session): grafo LangGraph compilado, sin databricks-agents, prompts en agent/prompts/ con hash + tests | Nicolle | Mié 30 |
| M7 | eval/metrics.md + eval/cases.jsonl | Nicolle | Vie 2 |
| M8 | contracts/ops.yaml | Eladio, Nicolle | Jue 1 |

## Eladio ↔ Nicolle
| # | Entregable | De → para | Fecha |
| --- | --- | --- | --- |
| X1 | Workspace, sp-agent-ro, secreto en Key Vault, wh-agent; + CAN_EDIT de sp-agent-ro solo sobre /Shared/fh26/agente (mock: experimento personal de Manuela) | Eladio → Nicolle, Manuela | Lun 28; permiso MLflow Mié 30 mañana |
| X2 | Asset Bundles desde GitHub Actions | Nicolle → Eladio | Mar 29 |
| X3 | Export App Insights → ops.infra_requests; tablero AI/BI con p95 en caliente y cold start por separado | Nicolle → Eladio | Vie 2 |

## Calendario
| Día | Eladio | Manuela | Nicolle | Sync |
| --- | --- | --- | --- | --- |
| Lun 28 | E1, X1 | M1, M2, esqueleto | N1, N2 | 21:00 contratos firmados |
| Mar 29 | E5, E6, E7 inicio | M3–M5, corpus, reglas | N2, N3, N4, X2 | — |
| Mié 30 | E2, E3, E7, X1 (permiso MLflow) | M6, caso normal | N2, N5 | Integración 1 |
| Jue 1 | E4 | modelos + baselines, Jev, M8 | N6 | — |
| Vie 2 | E8 | ambiguo/escalamiento, PT, guardrails, eval, M7 | X3, N8 | — |
| Sáb 3 | README datos | harness, métricas | N7 | Integración 2 |
| Dom 4 | slides datos | README, slides arq. | video, setup | ensayo ×2 |
| Lun 5 | entrega | entrega | entrega | — |
