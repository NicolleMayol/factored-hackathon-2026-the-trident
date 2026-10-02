# 06-evaluacion

Owner: Manuela · v1 · 2026-09-28.

Eval set 300 casos (40/25/25/10; ES 60/PT 40) en pares actuar/abstener. Componentes con baseline: clasificador (TF-IDF+LogReg), pre-score (regla y LogReg), retrieval (BM25), agente (LLM solo). Matriz de confusión de acción: Act/Abstain/Paired Accuracy, CAR, SR/UR/IRR, FP rate de acción, Injection Violation Rate, AbsRec@K. Casos adversariales etiquetados con MITRE ATLAS. Judge validado con 50 juicios humanos. Salida del harness en MLflow y CI.

## Datos que entran al eval y datos que no (ADR-21, regla acordada con Factored 2026-10-01)

| Entra | No entra |
| --- | --- |
| Dataset de Factored (`gold.intent_labels`, `customer_360`, `customer_behavior_12m`) para macro-F1 y AUC | Cualquier tabla `ref.*` (tasas y topes de reguladores) como feature, label o caso |
| `eval/cases.jsonl` construido con los 5 clientes de prueba y el catálogo sintético `gold.credit_product_catalog` | Textos normativos como casos de prueba |
| Corpus sintético `gold.policy_chunks` para Recall@5 y groundedness | Datos externos consultados en vivo |

Las fuentes externas solo son contexto del RAG y techo del motor de reglas. Un test en CI (`eval/test_external_guard.py`) falla si una columna de `ref.*` aparece en `features` de `contracts/gold.yaml` o si un caso de eval declara origen externo.

Para ampliar este apartado usa el skill `adr-hackathon` (modo documentar).
