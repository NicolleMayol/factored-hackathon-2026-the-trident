---
name: adr-hackathon
description: Documentar o cambiar una decisión, contrato, métrica o dependencia del Agente Crédito LATAM (Factored Hackathon 2026) desde el rol datos, ia-ml o servicio. Pregunta primero lo técnico del rol, detecta impacto cruzado con contracts/impact-map.yaml y se detiene si otro rol debe enterarse antes de seguir. Usar ante "documentar mi parte", "añadir al ADR", "registrar una decisión", "cambiar un contrato", "¿a quién afecta esto?".
---

# ADR Hackathon — una sola voz, tres roles, cero reuniones

Produce apartados del ADR con la misma estructura, el mismo vocabulario y los mismos contratos, y garantiza que ninguna decisión con consecuencias para otro rol avance sin que ese rol se entere. Funciona en Claude Code, Claude.ai, Cowork, GitHub Copilot o cualquier agente que lea SKILL.md.

## Fuente de verdad (léela antes de escribir)
1. `docs/adr/README.md` — índice y glosario.
0. `diagrams/arquitectura.drawio` (XML sin comprimir), `diagrams/styles.yaml` (catálogo de iconos) y `diagrams/README.md` — la fuente de verdad visual.
2. `contracts/impact-map.yaml` — quién posee y quién consume cada elemento. Es el corazón del gate de impacto.
3. `contracts/*.yaml` y `contracts/handoff.schema.json` — gold, tools, api, chunks, ops, infra.
4. `policy/policy.yaml`, `policy/catalog.yaml`, `policy/glossary.yaml`.
5. `docs/adr/decisions.md` (ADR-01…NN) y `docs/adr/dependencies.md` (E/N/M/X + calendario).

Nunca inventes nombres de tablas, tools, endpoints, App Settings o métricas. Si no existen, propón una decisión ABIERTA y añade el elemento a `impact-map.yaml`.

## Modos
- `documentar` — nuevo apartado o actualización (flujo completo).
- `impacto` — solo responder "¿a quién afecta este cambio?" (pasos 1, 3 y 4; no escribe archivos).
- `diagramar` — añadir o cambiar componentes en `diagrams/arquitectura.drawio` con los iconos del catálogo, coherente con contratos y ADR (sección "Diagramar" al final).

## Flujo obligatorio

### Paso 1 — Rol y tipo (una sola pregunta con opciones)
- Rol: `datos` (Eladio) · `ia-ml` (Manuela) · `servicio` (Nicolle).
- Tipo: `decisión nueva` · `actualizar decisión` · `contrato` · `métrica/observabilidad` · `dependencia` · `what's missing`.
- Modo: `documentar` · `impacto`.

### Paso 2 — Preguntas técnicas del rol (no generes nada antes de las respuestas)
Acepta "no aplica". Si una respuesta contradice un contrato existente, dilo antes de seguir.

**datos**
1. Tabla o pipeline: capa (bronze/silver/gold/ref/ops), grano, llave, partición.
2. Contrato de esquema: columnas nuevas o cambiadas, tipos, nulabilidad, `_ingested_at`.
3. Reglas de calidad y dónde se registran (`ops.dq_results`). Frescura máxima.
4. Llegada tardía y evolución de esquema: ¿fixture?
5. Leakage: fecha de corte; columnas prohibidas en features (género, estado civil, edad).
6. Fuente externa: URL, fecha de snapshot, licencia, `es_sintetico`.
7. ¿A quién bloquea y con qué mock se avanza mientras llega?

**ia-ml**
1. Nodo o componente: Understand / Decide / Act / Verify / Escalate / Respond / tool / modelo / eval.
2. Qué lee y qué escribe: tools, tablas gold, endpoints, versión de prompt o modelo.
3. ¿Cambia la matriz de política o los scopes? Regla y base regulatoria.
4. Verificación de la salida: groundedness, cita a chunk o regla, test.
5. Métrica afectada (matriz de confusión de acción, Recall@5, macro-F1, p95, costo por caso) y por idioma.
6. Baseline y split.
7. Qué queda To-Be.

**servicio**
1. Recurso Azure/Databricks: nombre, SKU o plan, región, free tier sí/no.
2. Secretos y accesos: Key Vault, App Settings (nombres exactos), service principal, scopes.
3. Contrato de API: endpoint, request/response, códigos de error, `trace_id`.
4. Resiliencia: retries acotados, timeout, circuit breaker, fallback (= escalar).
5. Observabilidad: señal, sink (`ops.*`), alerta y umbral.
6. CI/CD: job, gate, quién mergea.
7. Capacidad: resultado de carga (usuarios, p50/p95, error rate) o límite conocido.

### Paso 3 — Análisis de impacto (obligatorio, antes de generar nada)
1. Lee `contracts/impact-map.yaml`.
2. Para cada elemento que el aporte toca, produce la tabla:

   | Elemento | Estado (existe / nuevo / cambia) | Owner | Consumers afectados | Qué deben hacer | Fecha límite |
   | --- | --- | --- | --- | --- | --- |

3. Elemento nuevo → añade su entrada a `impact-map.yaml` (owner, consumers, used_by) en el mismo PR.
4. Cambio de contrato → nueva versión del archivo, fecha y a quién avisar.

### Paso 4 — GATE DE IMPACTO CRUZADO (detente aquí si aplica)
Si algún consumer ≠ rol del autor:
- **No continúes con implementación ni con más documentación.** Muestra al usuario, en este orden:
  1. La tabla de impacto del paso 3.
  2. Un aviso listo para pegar, por rol afectado, con esta forma:
     `@<github> · <rol>: <qué cambia> · <qué debes hacer> · <para cuándo> · <qué se rompe si no>`.
  3. Las filas de `dependencies.md` que cambian (fecha, entregable o mock).
- Pregunta una sola cosa: "¿Publico el PR con este aviso, o ajustamos la decisión para evitar el impacto?".
- Solo tras la respuesta sigue al paso 5. El workflow `adr-impact` bloqueará el merge hasta que los impactados aprueben; el skill no lo sustituye, lo alimenta.

Si ningún consumer es distinto del autor: dilo en una línea y sigue.

### Paso 5 — Generar el apartado (plantilla fija)
```
## <Título>  ·  rol: <datos|ia-ml|servicio>  ·  <fecha>  ·  estado: <cerrada|abierta>

**Decisión.** Una frase.

| Alternativas descartadas | Por qué |
| --- | --- |

**Impacto.** La tabla del paso 3.

**Cómo se prueba.** Métrica, umbral, dónde se registra (MLflow / ops.* / CI).

**Hackathon vs To-Be.** Dos columnas.

**Dependencias.** Filas nuevas o cambiadas de dependencies.md (#, entregable, de → para, formato, fecha, mock).

**Base regulatoria (si aplica).** Norma y país, "a validar con legal".
```

### Paso 6 — Entregar
- Escribe en `docs/adr/<sección>.md`; añade la fila ADR-NN a `decisions.md`; actualiza `dependencies.md` e `impact-map.yaml`.
- Abre PR con título `adr(<rol>): <título>` usando la plantilla del repo; pega el aviso del paso 4 en la sección "Aviso a los roles afectados" (el workflow lo exige).
- Deja un resumen de 5 líneas para el canal del equipo: qué cambió, a quién afecta, para cuándo, qué se rompe si no, enlace al PR.

## Reglas de estilo
- Vocabulario fijo: nodo, tool, policy engine, handoff, trace_id, gold/ref/ops, versión C, matriz de confusión de acción, banda libre/condicionada/cerrada, To-Be.
- La métrica de no agencia es la matriz de confusión de acción (Act/Abstain/Paired Accuracy, CAR, SR/UR/IRR, FP rate, Injection Violation Rate, AbsRec@K). Nunca "MAT/MAD".
- Dato externo: URL, fecha, licencia, `es_sintetico`. Ningún dato del dataset sale del tenant.
- Costos: estimación por 7 días, nunca cotización. Español, frases cortas, tablas, sin adjetivos.
- Lo que no cabe en el hackathon va a To-Be y a "what's missing"; nunca se omite.

## Diagramar (modo `diagramar`)
Todo cambio de arquitectura se dibuja en el mismo archivo, con los mismos iconos, y queda atado a los contratos. Nunca se crea un diagrama nuevo fuera de `diagrams/arquitectura.drawio`.

1. **Antes de dibujar**: pasos 1 a 4 del flujo (rol, tipo, preguntas, impacto). Un componente nuevo sin entrada en `impact-map.yaml` no se dibuja: primero la entrada, luego la celda.
2. **Lee** `diagrams/arquitectura.drawio` y `diagrams/styles.yaml`. Si el archivo está comprimido (texto base64 dentro de `<diagram>`), ejecuta `python scripts/drawio_tool.py decompress` y avisa.
3. **Página**: `hackathon` (lo que se despliega), `to-be` (teórico), `agente-runtime`, `datos`, `observabilidad`. Un cambio de estado hackathon → to-be se mueve de página, no se duplica.
4. **Estilo**: usa el `style` y tamaño exactos de `styles.yaml` para el servicio (Azure, Databricks, AWS, genérico). Si no existe icono para ese servicio, propón uno de la librería oficial de draw.io (`shape=mxgraph.azure2.*`, `mxgraph.aws4.*`) y añádelo al catálogo en el mismo PR. Colores de flechas según la leyenda del archivo (extracción azul, transformación verde, ML/IA magenta, aplicación cian, usuario naranja, Unity Catalog rosa). Nada de estilos ad hoc.
5. **Atributos obligatorios** en cada celda relevante (celda `<object>` con `label`, no `<mxCell value>`): `element` (id del impact-map), `adr` (ADR-NN), `owner` (datos | ia-ml | servicio), `estado` (hackathon | tobe). Las flechas llevan `label` con el verbo (lee, escribe, invoca, traza) y `element` del contrato que representan cuando aplica (`api.POST_/chat`, `tools.*`).
6. **Edición del XML**: ids nuevos con prefijo del rol y fecha (`ia-20260929-1`); no reordenes ni reformatees celdas ajenas; geometría alineada a la grilla de 10 px y dentro del contenedor (`parent`) correcto; conectores con `source` y `target`, nunca puntos sueltos.
7. **Verificación**: ejecuta `python scripts/drawio_tool.py sync diagrams/arquitectura.drawio`; corrige hasta que no haya elementos sin entrada. Si hay exportador local (`drawio` CLI), exporta PNG y míralo; si no, dilo y deja la exportación a CI.
8. **Entrega**: el PR incluye el `.drawio`, la fila del ADR, el impact-map y, si cambió un contrato, el aviso del paso 4. En el apartado del ADR referencia la imagen por su ruta fija `diagrams/out/arquitectura-<página>.png`.
