# Agente Crédito LATAM · Factored AI & Data Hackathon 2026

Agente de servicio al cliente para un banco regional (México, Colombia, Argentina) enfocado en un workflow: información de productos de crédito y elegibilidad, en español y portugués. Informa y simula; nunca decide crédito. Sabe cuándo no actuar y lo demuestra con números.

## Cómo funciona
- Grafo de estados Understand → Decide → Act → Verify → Escalate (LangGraph) en Azure Function App. Decide es determinista: matriz de política en `policy/policy.yaml`, scopes del token y flags del cliente.
- Tres componentes separados: LLM (conversación, Databricks Foundation Model APIs), pre-scoring LightGBM (insumo del motor, nunca decide) y reglas de elegibilidad versionadas (única fuente del resultado).
- RAG sobre políticas y catálogo sintéticos (etiquetados como tales), vector store y estado en Azure Cosmos DB. Toda cifra en una respuesta traza a un chunk o a un resultado de tool.
- Datos: medallón bronze/silver/gold en Databricks (Unity Catalog) sobre el dataset LATAM Bank; contratos de esquema, calidad y frescura en `contracts/`.

## Evidencia
Eval set held-out ES/PT en pares actuar/abstener; dos componentes aprendidos evaluados contra baseline; matriz de confusión de acción (Act/Abstain/Paired Accuracy, CAR, Informed Refusal Rate, FP rate de acción, Injection Violation Rate); p50/p95 y costo por caso. Resultados en `eval/` y en el ADR.

## Documentación
| Qué | Dónde |
| --- | --- |
| Decisiones de arquitectura (ADR-01…NN) | `docs/adr/decisions.md` y `docs/adr/*.md` |
| Contratos: tablas gold, tools, API, handoff, chunks, telemetría, infra | `contracts/` |
| Matriz de política y glosario ES↔PT | `policy/` |
| Diagramas (fuente draw.io y exportes) | `diagrams/` |
| Dependencias y calendario del equipo | `docs/adr/dependencies.md` |

## Ejecutar
Instrucciones de setup, despliegue y evaluación reproducible en `docs/adr/09-servicio.md` y `docs/adr/06-evaluacion.md` (se completan durante el sprint).

## Equipo
Eladio Yovera (datos) · Manuela Larrea (IA/ML) · Nicolle Mayol (servicio). Documentación como código: cada decisión entra por PR con análisis de impacto (`AGENTS.md`, `.claude/skills/adr-hackathon`).
