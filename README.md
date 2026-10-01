# Agente Crédito LATAM · Factored AI & Data Hackathon 2026

Agente de servicio al cliente para un banco regional (México, Colombia, Argentina) enfocado en un workflow: información de productos de crédito y elegibilidad, en español y portugués. Informa y simula; nunca decide crédito. Sabe cuándo no actuar y lo demuestra con números.

## Cómo funciona
- Grafo de estados Understand → Decide → Act → Verify → Escalate (LangGraph) en Azure Function App. Decide es determinista: matriz de política en `policy/policy.yaml`, scopes del token y flags del cliente.
- Tres componentes separados: LLM (conversación, Databricks Foundation Model APIs), pre-scoring LightGBM (insumo del motor, nunca decide) y reglas de elegibilidad versionadas (única fuente del resultado).
- RAG sobre políticas y catálogo sintéticos (etiquetados como tales), vector store y estado en Azure Cosmos DB. Toda cifra en una respuesta traza a un chunk o a un resultado de tool.
- Datos: medallón bronze/silver/gold en Databricks (Unity Catalog) sobre el dataset LATAM Bank; contratos de esquema, calidad y frescura en `contracts/`.

## Dónde hay IA y dónde no
| Paso | Quién decide | Por qué |
| --- | --- | --- |
| Entender intención e idioma | LLM pequeño (Llama 8B) con salida JSON tipada; baseline TF-IDF + regresión logística | lenguaje libre en es y pt; se mide macro-F1 por idioma |
| Decidir qué se puede hacer | Reglas YAML versionadas × scopes del token × banda regulatoria; sin LLM | reproducible, auditable, con base normativa por país |
| Ejecutar | Tools tipadas, solo las autorizadas; pre-scoring LightGBM como insumo | el modelo informa, nunca aprueba |
| Verificar | LLM grande (Claude Sonnet) exige cita por cifra; máx. 2 reintentos | sin cita no se afirma |
| Escalar | Humano, siempre en banda cerrada | abstenerse cuenta como acierto |

## Trade-offs explícitos
| Eje | Decisión | Qué se sacrifica |
| --- | --- | --- |
| Autonomía | El agente informa y pre-evalúa; nunca aprueba ni niega crédito | menos "wow" de automatización |
| Exactitud | Toda cifra cita un chunk o una regla; tasa ≤ usura verificada | respuestas más cortas y con más escalamientos |
| Latencia | p95 ≤ 8 s en caliente; cold start reportado aparte; scale-to-zero fuera de la ventana de evaluación | primer turno lento tras inactividad |
| Costo | Free tiers y serverless (versión C, ≈ 35–125 USD / 7 días) | sin always-on; límites de RU/s |
| Supervisión humana | Handoff con contexto completo y motivo (`escalate_reason`); vista de analista | parte de los casos no se resuelve en el chat |

## Fuentes externas y su justificación
El dataset trae clientes, productos y transacciones, pero no lo que la regulación obliga a decir al cliente (tasa de usura, CAT, CFT, TEA de referencia). Esas cifras públicas de BCRA, Superintendencia Financiera de Colombia y Banxico entran por batch, con URL y fecha de snapshot, solo como contexto del RAG y techo del motor de reglas. Ninguna fuente externa se usa para entrenar ni para evaluar: las métricas se calculan sobre el dataset y un catálogo sintético, y un test en CI lo verifica. Detalle fuente por fuente en `docs/adr/12-fuentes-externas.md`.

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
| Clientes de prueba y usuario analista | `docs/test-users.md` |
| Insights sobre el dataset (demanda de crédito por país e idioma, segmentos) | `data/` (notebook E10) |

## Ejecutar
Instrucciones de setup, despliegue y evaluación reproducible en `docs/adr/09-servicio.md` y `docs/adr/06-evaluacion.md` (se completan durante el sprint).

## Equipo
Eladio Yovera (datos) · Manuela Larrea (IA/ML) · Nicolle Mayol (servicio). Documentación como código: cada decisión entra por PR con análisis de impacto (`AGENTS.md`, `.claude/skills/adr-hackathon`).
