# Diagramas como código (draw.io)

Fuente de verdad visual: `diagrams/arquitectura.drawio` (XML **sin comprimir**: en draw.io, Archivo → Propiedades → desmarcar "Comprimido"). Páginas: `hackathon`, `to-be`, `agente-runtime`, `datos`, `observabilidad`. Nadie edita PNG a mano: se exportan en CI.

## Cómo se mantiene coherente con el ADR
1. Cada componente relevante lleva **atributos de datos** (clic derecho → Editar datos): `element` = id de `contracts/impact-map.yaml` (ej. `infra.cosmos`), `adr` = decisión que lo justifica (ej. `ADR-04`), `owner` = datos | ia-ml | servicio, `estado` = hackathon | tobe.
2. `scripts/drawio_tool.py sync` compara esos atributos con el impact-map y falla si un componente dibujado no existe en los contratos (o avisa si un contrato no está dibujado). Corre en CI (`diagram-sync`).
3. Los iconos y estilos se reutilizan desde `diagrams/styles.yaml` (catálogo extraído del archivo de Eladio). Regla: nunca un icono nuevo si ya existe uno para ese servicio.
4. El skill `adr-hackathon`, modo `diagramar`, edita el XML: añade o cambia celdas con estilos del catálogo, escribe los atributos y ejecuta `sync` antes de proponer el PR.
5. En cada PR que toca `diagrams/`, CI (`diagram-sync`) valida y deja los PNG como artifact `diagramas-png` para revisar. Al mergear un cambio en un `.drawio`, `main.yml` (`diagram-export`) exporta `diagrams/out/*.png` con `rlespinasse/drawio-export-action` y los sube a main con la GitHub App del equipo, que está en el bypass del ruleset de main. Nadie sube PNG a mano. El ADR y las páginas los referencian por ruta fija.

## Herramientas para cada persona
| Herramienta | Uso |
| --- | --- |
| VS Code + extensión `hediet.vscode-drawio` | abrir y editar `.drawio` dentro del repo, ver diff del XML |
| draw.io desktop / app.diagrams.net | edición visual; guardar sin comprimir |
| Claude Code / Claude desktop con la carpeta del repo | "dibuja el cambio X en la página hackathon" → el skill edita el XML y corre sync |

## Qué se etiqueta y qué no
Se etiquetan con `element` los componentes de infraestructura y servicio (Cosmos, Function, App Service, Databricks, warehouse, serving, FM APIs, identidad, Key Vault, CI/CD, storage, pipelines). Las tablas gold, endpoints de API y políticas viven en `contracts/` y no se dibujan: el `sync` los lista como "sin dibujar" solo a título informativo y no falla por ellos.

## Cambios aplicados el 2026-09-29 sobre el archivo de Eladio (página DEMO)
- Etiquetas de datos en 17 celdas + 5 en ENTERPRISE (`estado=tobe`).
- Relabel: Cosmos "Serverless" → "Free tier (estado + vectores)"; "Agent RAG" → "Foundation Model APIs (LLM)"; "Lakeflow Connect" → "Auto Loader (SDP) desde S3"; typos en la lista de recursos.
- Nuevo: caja "SQL Warehouse wh-agent · sp-agent-ro" bajo Vector Store (ids `ia-20260929-1..3`).
- Nuevas aristas: Function → Warehouse ("lee gold") → gold; Function → MLflow ("trazas"); Lakeflow Jobs → Cosmos ("carga chunks"); Function → Cosmos ("lee/escribe").
Revisar posiciones en draw.io: las aristas nuevas usan enrutado ortogonal automático y pueden necesitar un ajuste manual de waypoints.
