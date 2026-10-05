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
| Entender intención e idioma | Guardrail determinista (regex es/pt/en) antes del modelo; luego Llama 3.3 70B con salida JSON tipada (`understand_v2`); baseline TF-IDF + regresión logística (macro-F1 0,92) | lenguaje libre en es y pt; una inyección nunca llega al LLM |
| Decidir qué se puede hacer | Reglas YAML versionadas × scopes del token × banda regulatoria; sin LLM | reproducible, auditable, con base normativa por país |
| Ejecutar | Tools tipadas, solo las autorizadas; pre-score (regresión logística con features de cartera, AUC 0,78 sobre 134 k clientes) como insumo | el modelo informa, nunca aprueba; ganó al LightGBM por simplicidad a igual AUC |
| Verificar | Check determinista: toda cifra debe existir en una cita o un hecho verificado; Respond redacta con Llama 3.3 70B y, si el check falla, responde con la plantilla | sin cita no se afirma |
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

## Evidencia (números del 5 de octubre)
| Qué | Cómo se midió | Resultado |
| --- | --- | --- |
| Matriz de confusión de acción, todo real (Llama 3.3 70B, `understand_v2`, gold por SQL, trazas, pre-score) | 82 casos es/pt en pares actuar/abstener, 15 adversariales MITRE ATLAS, usuarios = clientes reales de gold (`eval/pick_users.py`, `eval/run_eval.py`) | act accuracy 0,86 · abstain accuracy 0,94 · paired 0,83 · FP de acción 0,057 · IVR 0 · groundedness 1,0 · 7 fallas de borde de intención (`¿Califico?` → confirmar en vez de aclarar) · umbrales ok |
| Misma matriz con el fixture (`data/mock`, SQL en mock) | mismos 82 casos | act 0,90 · abstain 1,0 · FP 0 · 3 fallas; la diferencia con la fila anterior es intención del LLM sobre mensajes de borde, no datos |
| Hallazgo del eval con SQL real | primera corrida sobre gold: abstain 0,68, FP de acción 0,32 | los `TEST-*` de gold no tenían productos ni comportamiento → P07 nunca disparaba; corregido con clientes reales por condición y `scripts/seed_test_customers.py` para los usuarios de la UI |
| Guardrail determinista | mismos 15 adversariales, con y sin la capa regex antes del LLM | IVR 0,267 → 0 en los 4 endpoints probados |
| Comparación de modelos en Understand | mismo harness, 4 endpoints pay-per-token (`eval/models.md`) | llama-3.3-70b: menos fallas y p95 la mitad que gpt-oss; se eligió con el número |
| Prompt v1 → v2 | 11 fallas → 3, FP de acción 0,13 → 0 | la mejora vino del prompt, no del modelo |
| Retrieval híbrido (vector + BM25 + RRF, enrutado por sección) | 24 preguntas con chunk esperado (`eval/retrieval_eval.py`) | Recall@5 con bge-m3 fp32: ES 1,0 · PT 0,917 |
| Clasificador de intención (baseline) | TF-IDF char 2–5 + LogReg, 109 frases sintéticas → 60 mensajes únicos del held-out | macro-F1 0,92 (es 0,94 · pt 0,89); sus errores son los que el guardrail resuelve |
| Pre-score | 134.037 clientes reales de gold; target proxy declarado (sin mora > 30 d); 4 experimentos en MLflow | logística v1 0,66 → **v2 con cartera 0,78**; LightGBM 0,66 → 0,78: las features valen 0,12 de AUC, el modelo 0 |
| Costo y latencia por turno | 82 turnos reales del eval, trazas en `ops.agent_turns` | 0,00035 USD/turno · p50 3,3 s · p95 9,7 s (dos llamadas al 70B; ≈ 0,9 s por consulta a gold); primer turno ≈ 15 s si el warehouse está frío |
| Pre-score en runtime | mismo cliente por endpoint (`prescore-lgbm`) y en proceso (`policy/prescore_logreg.json`) | paridad exacta (p = 0,969, mismo SHAP); endpoint frío > 25 s (timeout controlado), caliente 5,5 s con las 3 consultas a gold; por eso producción corre `prescore=local` |

## Qué falta y por qué (what's missing)
| Pieza | Estado | Motivo | Qué haría falta |
| --- | --- | --- | --- |
| Model Serving (`prescore-lgbm`, `embed-bge-m3`) | workspace en Premium; `prescore-lgbm` READY y verificado; `embed-bge-m3` recreado en `Medium` (en `Small` no pasó la prueba de salud: bge-m3 fp32 + int8 al cargar no cabe en 4 GB) | CAN_QUERY de `sp-agent-ro` pendiente (`ml/serving.py --grant`) | flip `embed`/`store` a real en `agent_modes` cuando el endpoint esté READY con el grant |
| Embeddings reales en runtime | medidos en local (bge-m3) y usados para cargar Cosmos; el agente desplegado usa BM25 + enrutado por sección + vector hash | sin endpoint no hay vector de consulta; meter bge-m3 (2 GB) en la Function rompe el arranque ≤ 30 s | el mismo endpoint |
| Held-out sobre el dataset | no entrenable: 42 frases plantilla bajo las 6 categorías (`docs/labels.md`) | el dataset no distingue los cinco intents del workflow 4 | etiquetas reales de transcripciones |
| Topes de CO y MX | valor provisional, no citado | la SFC publica PDF mensual y Banxico consulta interactiva | pegar dos números por fila (E6) |
| Portugués en el dataset | 100 % español | el dataset es MX/CO/AR | PT se mide con corpus y casos sintéticos, declarado |

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
