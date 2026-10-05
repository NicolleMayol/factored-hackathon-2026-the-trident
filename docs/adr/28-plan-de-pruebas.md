# 28-plan-de-pruebas

Owner: Nicolle (servicio), con ia-ml y datos · v1 · 2026-10-05.

## ADR-28 · Plan de pruebas guiado por modos de falla  ·  rol: servicio  ·  2026-10-05  ·  estado: abierta

**Decisión.** Las pruebas del sistema se eligen por riesgo: un inventario de modos de falla con número de prioridad de riesgo (NPR = severidad × ocurrencia × detección), contrastado contra las características de ISO/IEC 25010 para no dejar huecos. Los casos del agente se diseñan con tablas de decisión y valores límite sobre `policy/policy.yaml`, y se miden con los umbrales que ya existen (GQM). Se implementa primero lo de NPR más alto que cabe antes de la entrega.

### Por qué esta mezcla

| Marco | Qué aporta aquí | Qué no resuelve solo |
| --- | --- | --- |
| Modos de falla (AMFE, NPR) | Prioriza: dice qué probar primero con poco tiempo | No garantiza cobertura de todas las calidades |
| ISO/IEC 25010 | Lista de control: adecuación, fiabilidad, seguridad, rendimiento, usabilidad, mantenibilidad | No prioriza |
| Tablas de decisión y valores límite | Casos exactos para el motor de reglas (P01–P11) y los umbrales del catálogo | Solo sirve donde hay reglas explícitas |
| GQM | Ata cada objetivo a una métrica con umbral (`eval/metrics.py`, `contracts/ops.yaml`) | No dice cómo generar los casos |

### Escala (1–5)

| Valor | Severidad (S) | Ocurrencia (O) | Detección (D) |
| --- | --- | --- | --- |
| 1 | Cosmético | Casi imposible | Una prueba en CI lo detecta siempre |
| 3 | El cliente recibe una respuesta mala o el demo se cae | Pasó en pruebas o es plausible | Se detecta a mano o tarde |
| 5 | Daño al cliente, regla legal violada o datos expuestos | Ya pasó en producción | Nada lo detecta hoy |

## Inventario de modos de falla (ordenado por NPR)

| ID | Componente | Modo de falla | Efecto | S | O | D | NPR | Hoy lo cubre | Prueba propuesta | Dueño |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F08 | Agente ↔ dependencias | Una dependencia en frío (warehouse, serving, FM APIs) supera el timeout y la Function responde 500 | El cliente ve un error en vez de un escalamiento | 4 | 4 | 3 | 48 | `tools.yaml` define frío y fallback; smoke solo `/healthz` | Caos controlado: adaptadores con latencia y error inyectados → la acción debe ser `escalate` con `case_id`, nunca 500 | ia-ml + servicio |
| F03 | Respuesta | Una cifra en la respuesta no está en el chunk citado | El cliente recibe un dato inventado | 4 | 3 | 3 | 36 | groundedness en eval | Verificador determinista: cada número del texto aparece en un chunk citado o en el catálogo; si no, `escalate` | ia-ml |
| F09 | Identidad del agente | Falta un permiso de `sp-agent-ro` (FM APIs, serving, SQL, `ops`) | 403 en producción; ya pasó 3 veces el 5 oct | 4 | 4 | 2 | 32 | `scripts/check_access.py` (manual) | Correr `check_access.py` A1–A7 con la identidad de la Function en el smoke de `main.yml`, después del apply | servicio |
| F02 | Guardrails | Inyección o pedido de datos de terceros pasa el filtro (paráfrasis, portugués, mayúsculas) | El agente sale de su política | 5 | 3 | 2 | 30 | `test_guardrails` (4), 15 casos adversariales, IVR = 0 | Mutar cada caso adversarial (paráfrasis, idioma, ofuscación) y exigir IVR = 0 | ia-ml |
| F12 | Repo | Un secreto llega al repo público o a un log | Acceso a Azure o Databricks | 5 | 2 | 3 | 30 | Nada automático | `gitleaks` en `pr.yml` | servicio |
| F13 | Repo | Filas del dataset llegan al repo público | Incumple la regla de Factored (ADR-12) | 5 | 2 | 3 | 30 | `eval/test_external_guard.py` (solo `ref.*`) | Check en `pr.yml`: ningún `.csv/.jsonl` nuevo fuera de una lista permitida; patrón de ids reales del dataset | datos + servicio |
| F15 | Rendimiento | p95 en caliente > 8 s | Demo lenta para el jurado | 3 | 3 | 3 | 27 | Nada (N7 pendiente) | k6 con 10/25/50 usuarios contra la Function; p95 y error rate contra `ops.yaml` | servicio |
| F16 | Handoff | El paquete llega sin hechos ni evidencia | El analista repite preguntas | 3 | 3 | 3 | 27 | Esquema `handoff.schema.json` | Si corrió una tool, `verified_facts` y `evidence` no pueden estar vacíos | ia-ml |
| F20 | Costo | Los DBUs o el serving se disparan (Premium desde el 5 oct) | Presupuesto agotado antes de los resultados | 3 | 3 | 3 | 27 | Alerta de presupuesto al 50 % | Consulta diaria a `system.billing.usage` con umbral | servicio |
| F05 | Motor de reglas | Un umbral se aplica mal en el borde (puntaje 600, mora 30 días, monto máximo, cuota 40 %) | Resultado preliminar equivocado | 4 | 3 | 2 | 24 | `test_policy_engine` (20) | Valores límite: 599/600/601, 30/31 días, `amount_max` y `amount_max + 1`, cuota 40 %/40,1 % | ia-ml |
| F01 | Respuesta | El agente aprueba, niega o promete un crédito | Viola la regla central del producto | 5 | 2 | 2 | 20 | eval (FP rate), prompt de respond | Lista de frases prohibidas verificada en cada respuesta (es/pt) | ia-ml |
| F06 | Idioma | Responde en un idioma distinto al del mensaje | Mala experiencia | 2 | 3 | 3 | 18 | `test_scenarios` (idioma del perfil) | Métrica de idioma de respuesta por caso del eval | ia-ml |
| F07 | Decisión | Escala de más o de menos | Asesores saturados o casos sin revisión | 3 | 3 | 2 | 18 | eval: UR ≤ 0,15, CAR ≥ 0,85 | Ya cubierto; ampliar el set de 82 a los 300 casos de ADR-06 | ia-ml |
| F10 | UI ↔ API | La UI usa una ruta o campo que la API no tiene | Pantalla rota | 3 | 3 | 2 | 18 | `test_meta`, smoke de UI y `/meta` | Ya cubierto | servicio |
| F11 | Pipeline | Se despliega una capa fuera de orden (la UI sale aunque infra falle) | Versión inconsistente | 3 | 2 | 3 | 18 | `actionlint` | Agregar `infra` a los `needs` de `web` en `main.yml` | servicio |
| F14 | Datos | Gold desactualizado o con DQ fallido | Respuestas con datos viejos | 3 | 3 | 2 | 18 | `test_medallon` (18), `ops.dq_results` | Alerta de frescura (`freshness_h: 24`) que hoy no corre | datos |
| F19 | Infra | Drift entre Terraform y Azure | Un apply inesperado pide aprobación | 3 | 3 | 2 | 18 | Plan en cada PR | Plan programado diario que avise si hay cambios | servicio |
| F18 | UI | La UI falla en móvil o no es accesible | Parte del jurado no puede usarla | 2 | 2 | 3 | 12 | Capturas manuales con Playwright | Playwright + axe en CI contra el servidor mock | servicio |
| F17 | Sesión | `/session` emite el analista (`handoff:read`) a cualquiera | Lectura de handoffs con datos reales | 4 | 3 | 1 | 12 | Conocido (auditoría) | Documentar como demo-only; To-Be: Entra External ID | servicio |
| F04 | Consentimiento | Pre-evaluación sin autorización | Uso de datos sin permiso | 5 | 1 | 2 | 10 | `test_scenarios` (confirmación) | Tabla de decisión de P02 (abajo) | ia-ml |

## Cobertura ISO/IEC 25010

| Característica | Modos de falla | Estado |
| --- | --- | --- |
| Adecuación funcional (corrección) | F01, F03, F05, F06, F07, F16 | Cubierta por eval y tests; faltan valores límite y verificador de cifras |
| Fiabilidad (tolerancia a fallos, disponibilidad) | F08, F09, F11, F19 | El hueco más grande: nada prueba el comportamiento en frío ni los permisos en CI |
| Seguridad (confidencialidad, integridad, no repudio) | F02, F04, F12, F13, F17 | Guardrails cubiertos; faltan gitleaks y el check de datos en el repo |
| Eficiencia de desempeño | F15, F20 | Sin prueba de carga ni control de costo diario |
| Usabilidad y accesibilidad | F06, F18 | Solo revisión manual |
| Mantenibilidad (verificabilidad) | F10, F14 | Cubierta por CI |
| Compatibilidad | F10 | Cubierta (`/meta` + `ui.json`) |

## Tabla de decisión de la pre-evaluación (P02, P05, P07, P10, P11)

Cada fila es un caso de prueba. Se aplica de arriba abajo; la primera que coincide gana.

| # | JWT válido | `credit:simulate` | Inyección o tercero | Mora > 0 o fraude | Consentimiento | Resultado de reglas / IC del pre-score | Acción esperada | Regla |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | no | — | — | — | — | — | `reject` | P11 |
| 2 | sí | — | sí | — | — | — | `blocked` | P10 |
| 3 | sí | sí | no | sí | — | — | `escalate` (`risk_flag`) | P07 |
| 4 | sí | no | no | no | — | — | `escalate` (sin scope) | P02 |
| 5 | sí | sí | no | no | sin responder | — | `confirm` | P02 |
| 6 | sí | sí | no | no | no | — | `answer` sin datos del cliente | P02 |
| 7 | sí | sí | no | no | sí | Elegible / IC lejos del umbral | `answer` con resultado | P02 |
| 8 | sí | sí | no | no | sí | Revisión humana o IC cruza el umbral | `escalate` (`borderline`) | P05 |

Los valores límite de F05 se aplican dentro de las filas 7 y 8.

## GQM: objetivos y métricas

| Objetivo | Pregunta | Métrica (umbral) | Dónde |
| --- | --- | --- | --- |
| El agente actúa solo donde debe | ¿Abstiene cuando debe? ¿Actúa cuando puede? | abstain ≥ 0,90 · act ≥ 0,85 · paired ≥ 0,75 · FP de acción ≤ 0,10 | `eval/metrics.py` |
| Nadie lo saca de su política | ¿Pasa alguna inyección? | IVR = 0 · IRR ≥ 0,95 | `eval/metrics.py` |
| Escala bien | ¿Escala lo correcto, sin saturar? | CAR ≥ 0,85 · UR ≤ 0,15 | `eval/metrics.py` |
| Responde rápido y estable | ¿Cumple en caliente con carga? | p95 ≤ 8 s · error rate ≤ 2 % | `contracts/ops.yaml` |
| Nunca deja un resultado inseguro | ¿Hubo algún resultado inseguro? | `unsafe_outcomes` = 0 | `contracts/ops.yaml` |

## Plan

**Antes de la entrega (hoy), por NPR y esfuerzo:**

| Orden | ID | Prueba | Dueño | Esfuerzo |
| --- | --- | --- | --- | --- |
| 1 | F09 | `check_access.py` en el smoke de `main.yml` | servicio | 30 min |
| 2 | F11 | `infra` en los `needs` de `web` | servicio | 5 min |
| 3 | F12 | `gitleaks` en `pr.yml` | servicio | 20 min |
| 4 | F08 | Caos controlado en adaptadores: frío y error → `escalate` | ia-ml | 1 h |
| 5 | F15 | k6 con 10 usuarios contra la Function, antes de grabar el video | servicio | 30 min |
| 6 | F05 | Valores límite en `test_policy_engine` | ia-ml | 30 min |

**Después (To-Be):** F03, F02 (mutaciones), F13, F16, F20, F14, F19, F18 y ampliar el eval a 300 casos.

**Impacto.**

| Elemento | Estado | Owner | Consumers afectados | Qué deben hacer | Fecha límite |
| --- | --- | --- | --- | --- | --- |
| Plan de pruebas (este documento) | nuevo | servicio | ia-ml, datos | Revisar S/O/D de sus modos y aceptar o cambiar los dueños | lun 5 |
| `eval/` y `tests/` del agente | cambia (pruebas nuevas) | ia-ml | — | F08 y F05 hoy; F03, F02, F16 después | lun 5 / To-Be |
| `.github/workflows/` | cambia (F09, F11, F12, F15) | servicio | — | — | lun 5 |
| Pipelines y `ops.dq_results` | cambia (F14) | datos | — | Alerta de frescura | To-Be |

**Cómo se prueba.** Cada fila del inventario tiene una prueba que corre en CI, en el smoke o en un job programado. Cuando la prueba existe, su D baja a 1 y se recalcula el NPR. El plan se revisa al cerrar cada modo y antes de la ventana de jurado.

**Hackathon vs To-Be.**

| Hackathon | To-Be |
| --- | --- |
| NPR estimado por el equipo | NPR con datos de `ops.agent_turns` e incidentes |
| Caos controlado en tests con mocks | Fallas inyectadas en un ambiente de staging |
| k6 manual antes del video | Carga en cada release con umbral bloqueante |
| Eval de 82 casos | 300 casos (ADR-06), con pares por idioma |

**Dependencias.** Sin filas nuevas en `dependencies.md`; las tareas de la tabla de plan van como PR de cada dueño.
