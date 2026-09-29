# 10-observabilidad

Owner: todos · v1 · 2026-09-28 · Fuente completa: ADR compartido (Claude Doc) y página "Plan IA/ML Agente Crédito".

Un plano, cuatro dominios: infra (App Insights → ops.infra_requests, Nicolle), datos (ops.dq_results, Eladio), IA (MLflow Tracing → ops.agent_turns, Manuela), ML (inference tables → ops.ml_inference, Manuela). Todo con trace_id = operation_id. Tablero AI/BI en Databricks. Alertas en contracts/ops.yaml.

Para ampliar este apartado usa el skill `adr-hackathon` (modo documentar).
