# ADR — Agente Crédito LATAM · Factored Hackathon 2026

Fuente de verdad del diseño. Se edita por PR con el skill `adr-hackathon` (`.claude/skills/adr-hackathon/SKILL.md`). Vista compartida: Claude Doc "ADR — Arquitectura IA/ML Agente Crédito" y página "Plan IA/ML Agente Crédito".

## Secciones (una por archivo en `docs/adr/`)
| # | Archivo | Dueño principal |
| --- | --- | --- |
| 1 | 01-contexto.md | Manuela |
| 2 | decisions.md (ADR-01…NN) | todos |
| 3 | 03-contratos.md | todos (cambios solo vía `contracts/`) |
| 4 | 04-politica.md | Manuela |
| 5 | 05-regulacion.md | Manuela |
| 6 | 06-evaluacion.md | Manuela |
| 7 | 07-hackathon-vs-tobe.md | todos |
| 8 | 08-datos.md (medallón, DQ, frescura, fuentes) | Eladio |
| 9 | 09-servicio.md (infra, CI/CD, identidad, resiliencia, carga) | Nicolle |
| 10 | 10-observabilidad.md | Nicolle + Manuela + Eladio |
| 11 | 11-multilenguaje.md | Manuela |
| 12 | 12-fuentes-externas.md | Eladio |
| 13 | dependencies.md | todos |
| 14 | 18-agente-runtime.md (ADR-18: dónde corre el agente) | Manuela |
| 15 | 21-ajustes-ia-ml.md (ADR-21: embeddings, scopes, frío, fuentes externas) | Manuela |
| 16 | 22-esquemas-bronze-silver.md (ADR-22: contrato de bronze y silver, E9) | Eladio |

## Glosario
| Término | Significado |
| --- | --- |
| nodo | etapa del grafo: Understand, Decide, Act, Verify, Escalate, Respond |
| tool | función tipada que el agente puede llamar; permisos en la capa de tools |
| policy engine | evaluador determinista de `policy/policy.yaml` en el nodo Decide |
| handoff | paquete JSON para el agente humano (`contracts/handoff.schema.json`) |
| trace_id | identificador de la ejecución; igual al `operation_id` de App Insights |
| gold / ref / ops | esquemas de Unity Catalog: datos del agente / referencias externas / telemetría |
| versión C | vector store y estado en Cosmos DB free tier |
| matriz de confusión de acción | métrica de no agencia: acción esperada vs acción tomada |
| banda libre / condicionada / cerrada | grados de libertad regulatorios |
| To-Be | lo que se diagrama y se declara en "what's missing", no se construye |

## Reglas
- Ningún nombre nuevo de tabla, endpoint, tool o métrica sin cambio en `contracts/` y aviso a los otros dos roles.
- Solo Nicolle mergea a main. Un PR por apartado. Título `adr(<rol>): <título>`.
- Fechas, costos y fuentes siempre explícitos. Sin adjetivos.
