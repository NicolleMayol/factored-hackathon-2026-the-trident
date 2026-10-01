# 09-servicio

Owner: Nicolle · v3.2 · 2026-09-30 (stack `infra/databricks` desplegado, ADR-20).

## ADR-19 · Plan de infraestructura en Terraform  ·  rol: servicio  ·  2026-09-29  ·  estado: cerrada

**Decisión.** Servicio crea y opera toda la infraestructura de Azure y Databricks con Terraform, en East US 2. Datos e ia-ml trabajan dentro de esa plataforma y no crean recursos.

**Cambios v3 (2026-09-29, tras el primer despliegue).**
- Chat en **Static Web Apps Free** (`swa-agent-bank-dev`) en vez de Web App B1 + BFF: la suscripción tiene 0 de cuota de App Service B1, y con el JWT de prueba un BFF no protege nada extra.
- Terraform corre **solo en GitHub Actions** (workflow `infra`): plan en cada PR, apply en `main` con aprobación del environment `hackathon`. No hay `infra/bootstrap`: el workflow crea el storage del estado con `infra/scripts/ensure-backend.sh`.
- Identidad de CI: el SP `sp-deploy-iac-hackathon` que entregó Eladio, con secreto en GitHub **temporal**. Pasa a OIDC cuando Nicolle tenga Cloud Application Administrator en Entra ID. Roles del SP en la suscripción: Contributor, Storage Blob Data Contributor, User Access Administrator (con condición ABAC: solo asigna ese mismo rol) y Role Based Access Control Administrator (sin condición, otorgado por Nicolle el 2026-09-29 para que Terraform asigne roles).
- Secret scope `fh26` administrado por Databricks (no respaldado en Key Vault: ese tipo exige token de usuario y Terraform no corre desde una laptop). Terraform copia los valores desde Key Vault.
- Ingesta: el dataset de Factored se copia de S3 a ADLS (`landing`) con `azcopy` en el workflow `data-landing`. Las llaves de AWS solo viven en GitHub; Databricks lee de ADLS con el Access Connector.
- Desplegado el 2026-09-29: todo `infra/azure`. `infra/databricks` (2026-09-30, PR #9 y #10): storage credential, 8 external locations (6 esquemas, `landing` y `unity-catalog` para el catálogo), catálogo, esquemas, volúmenes, grants por esquema, `sp-pipelines`, `sp-agent-ro`, usuario de Manuela, `wh-agent`, scope `fh26`, experimento. El workspace no tenía metastore asignado: la cuenta ya tenía `metastore_azure_eastus2` (sin storage propio; uno por región) y Terraform lo asigna con el provider de cuenta y da al SP del pipeline `CREATE CATALOG`, `CREATE EXTERNAL LOCATION` y `CREATE STORAGE CREDENTIAL`. Para eso el SP es account admin, asignado a mano una vez por Nicolle (account admin desde el 2026-09-29), igual que su rol de RBAC.
- Solo serverless en Databricks, por tres razones: no hay clusters que administrar ni políticas que mantener, arranca en segundos, y la única razón para cómputo clásico (llaves de S3 en la config de Spark) desapareció con la copia a `landing`. Lakeflow Connect pide cómputo clásico solo en el gateway de CDC de bases de datos, que no usamos.

### Reparto
| Qué | Dueña/o |
| --- | --- |
| Azure: resource group, Key Vault, Log Analytics + App Insights, storage, Cosmos, Function App, Static Web App, presupuesto, identidad de CI | servicio |
| Databricks: workspace, ADLS Gen2 + Access Connector, storage credential + external location, catálogo `hackathon`, esquemas `bronze`/`silver`/`gold`/`ref`/`ops`/`ml`, grants del equipo, `sp-pipelines`, `sp-agent-ro`, secret scope `fh26`, `wh-agent`, experimento `/Shared/fh26/agente`, endpoints de Model Serving, config de FM APIs (endpoints, rate limits) | servicio |
| Tablas, pipelines medallón, DQ, Asset Bundles de datos | datos |
| Código del agente (`agent/`), prompts, modelo LightGBM y su versión, elección de LLM (ADR-02), eval | ia-ml |

### Recursos
Región: `eastus2` (Claude Sonnet 5 verificado por Nicolle el 2026-09-29). Nombres del diagrama DEMO de Eladio (`diagrams/arquitectura.drawio`); los que no están dibujados siguen la misma convención. Si un nombre global (storage, Key Vault, Cosmos) está tomado, se agrega un sufijo de 3 letras.

| Recurso | Nombre | SKU / plan | Notas |
| --- | --- | --- | --- |
| Resource group | `rg-ai-agents-dev` | — | uno para todo el hackathon |
| Estado Terraform | `rg-tfstate-agent-bank-dev`, `sttfstateagentbankdev` | Standard LRS, versionado | lo crea `infra/scripts/ensure-backend.sh` dentro del workflow |
| Key Vault | `kv-agent-bank-dev` | Standard, RBAC | secretos de la tabla "Secretos" |
| Log Analytics + App Insights | `log-analytics-agent-bank-dev`, `app-insight-agent-bank-dev` | pago por GB (5 GB/mes sin costo) | App Insights basado en workspace |
| Storage de la Function | `stfuncagentbankdev` | Standard LRS | `AzureWebJobsStorage` y contenedor de deploy |
| Function App | `func-agent-bank-dev` | Flex Consumption, Linux, python3.11, 2048 MB | máx. 10 instancias; always-ready 0 (1 en ventana de jurado); identidad administrada |
| Frontend | `swa-agent-bank-dev` | Static Web Apps Free | chat + vista `/handoff/{case_id}`; llama a la Function App desde el navegador (CORS) |
| Cosmos DB | `cosmos-agent-bank-dev` | NoSQL, free tier, capability `EnableNoSQLVectorSearch` | ver "Cosmos" |
| Databricks | `dbw-agent-bank-dev` | Premium trial (14 días), como en el diagrama | solo cómputo serverless |
| ADLS Gen2 | `adlsagentbankdev` | Standard LRS, HNS | contenedores `unity-catalog` (storage del catálogo), `landing` (copia de S3), `ops-export`, y uno por esquema: `bronze`, `silver`, `gold`, `ref`, `ops`, `ml-data` (el de `ml`; Azure pide 3 a 63 caracteres) (ADR-20) |
| Access Connector | `acc-agent-bank-dev` | — | identidad de Databricks sobre ADLS |
| SQL Warehouse | `wh-agent` | serverless 2X-Small, auto-stop 10 min | lectura de gold/ref |
| Presupuesto | `budget-agent-bank-dev` | — | alertas al 50/80/100 % de `budget_usd` |

### Cosmos
| Contenedor | Partition key | Throughput | TTL | Índice |
| --- | --- | --- | --- | --- |
| `conversations` | `/conversation_id` | 400 RU/s dedicado | 86400 s | por defecto |
| `handoffs` | `/case_id` | 400 RU/s dedicado | — | por defecto |
| `policy_chunks` | `/country` | 400 RU/s dedicado | — | vector `/embedding`, diskANN, 1024, cosine |

Cosmos no admite búsqueda vectorial en throughput compartido. Por eso cada contenedor tiene throughput propio: 1.200 RU/s, de los que el free tier cubre 1.000. Con menos de 1.000 vectores, diskANN hace full scan (más RU por consulta). El vector policy se crea con `azapi` si `azurerm` no lo expone.

### Estructura de Terraform
```
infra/
  azure/        azurerm + azapi: rg, kv, log/appi, storage, cosmos, function, static web app, dbw, adls, access connector, budget  (desplegado)
  scripts/      ensure-backend.sh: storage del estado, idempotente
  databricks/   provider databricks (lee el workspace por nombre): storage credential, external locations, catálogo, esquemas, volúmenes, grants, sp-agent-ro, sp-pipelines, secret scope, wh-agent, experimento; serving pendiente
```
Dos stacks porque el provider de Databricks necesita la URL del workspace antes de configurarse.

### Secretos y App Settings
| Secreto (Key Vault) | Lo usa |
| --- | --- |
| `databricks-client-secret` | Function App (`DATABRICKS_CLIENT_SECRET`) |
| `cosmos-key` | Function App (`COSMOS_KEY`), carga de chunks |
| `jwt-signing-key` | Function App (`JWT_SIGNING_KEY`) |
| — | Las llaves de S3 **no** están en Key Vault ni en Databricks: solo como secretos de GitHub (`S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`) para el workflow `data-landing` |

El scope `fh26` expone `cosmos-key` (carga de chunks a Cosmos, E7).

App Settings de la Function App (`contracts/infra.yaml` v3): los 12 de v2 más `APPLICATIONINSIGHTS_CONNECTION_STRING`. Los secretos van como referencias `@Microsoft.KeyVault(...)`; los nombres no cambian. Local: `local.settings.json` con los mismos nombres, fuera de git.

`sp-agent-ro` es un service principal de Databricks con secreto OAuth M2M. Grants: `USE CATALOG hackathon`, `USE SCHEMA` + `SELECT` sobre `gold` y `ref`, `CAN_USE` sobre `wh-agent`, `CAN_QUERY` sobre los endpoints de serving y FM APIs, `CAN_EDIT` sobre `/Shared/fh26/agente`. Sin escritura en datos.

El secret scope `fh26` lo administra Databricks. Terraform (stack `infra/databricks`) lee los valores de Key Vault y los escribe en el scope.

Grants del equipo:

| Identidad | Permisos |
| --- | --- |
| Nicolle | account admin; admin del workspace |
| `sp-deploy-iac-hackathon` (CI) | account admin; admin del workspace; `CREATE CATALOG`, `CREATE EXTERNAL LOCATION`, `CREATE STORAGE CREDENTIAL` en el metastore; dueño de lo que crea Terraform |
| Eladio | admin del workspace; `USE CATALOG hackathon`; `ALL PRIVILEGES` en `bronze`, `silver`, `gold`, `ref`, `ops`; `READ FILES` en `landing`; `CAN_USE` en `wh-agent` |
| `sp-pipelines` (SP con el que corren los Asset Bundles de datos, X2) | lo mismo que Eladio en datos; `READ` en el scope `fh26` |
| Manuela | `USE CATALOG hackathon`; `SELECT` en `gold` y `ref`; `USE SCHEMA`, `SELECT`, `CREATE TABLE` en `ops` (dueña de `agent_turns` y `ml_inference`); `ALL PRIVILEGES` en `ml`; `CAN_USE` en `wh-agent`; `CAN_MANAGE` sobre `/Shared/fh26/agente`; `CAN_QUERY` sobre serving y FM APIs (pendiente, con `prescore-lgbm`) |
| `sp-agent-ro` | `USE CATALOG hackathon`; `SELECT` en `gold` y `ref`; `CAN_USE` en `wh-agent`; `CAN_EDIT` en el experimento; sin escritura en datos |

Storage: `stg-credential-adlsagentbankdev` sobre `acc-agent-bank-dev` y una external location por container (`ext-loc-adlsagentbankdev-<container>`). El catálogo guarda en `unity-catalog/hackathon`; cada esquema en su container (`ml` en `ml-data`: Azure pide nombres de 3 a 63 caracteres). `landing` es de solo lectura. Catálogo, credential y external locations quedan aislados a este workspace.

### Identidad (cierra ADR-12)
Mock JWT. `POST /session` corre en la Function App, recibe uno de los 5 clientes de prueba (M3, `docs/test-users.md`) y firma HS256 con `JWT_SIGNING_KEY`. Claims: `customer_id`, `scopes`, `exp` (30 min). El nodo de auth valida firma y `exp`; `customer_id` solo sale del token. Entra External ID queda en To-Be.

El chat (Static Web App) llama a la Function App desde el navegador con el JWT. CORS en la Function App solo acepta el origen de la Static Web App. Los triggers HTTP van con `auth_level=ANONYMOUS` y validan el JWT en código (no hay dónde esconder una function key). `/handoff/{case_id}` y `/trace/{trace_id}` exigen un scope de agente humano en el JWT; el nombre del scope lo define ia-ml en `contracts/api.yaml`.

### Resiliencia
| Punto | Control |
| --- | --- |
| Tools | `contracts/tools.yaml`: timeout 8 s, 2 retries, circuit breaker a 5 fallos, fallback = escalar (ia-ml) |
| Cosmos | retries del SDK ante 429 |
| FM APIs | rate limit por endpoint en AI Gateway; valor tras N7 |
| Function App | máx. 10 instancias para acotar costo y llamadas a FM APIs |
| Model Serving | scale-to-zero fuera de la ventana de jurado; el cold start supera los 8 s de timeout y el turno escala |
| `/healthz` | revisa LLM, Cosmos, Model Serving y SQL Warehouse |
| SQL Warehouse | serverless apagado tarda en arrancar y puede pasar los 8 s de timeout de las tools; ver "Capacidad y límites" |

### Observabilidad
- App Insights → Log Analytics. `operation_id` = `trace_id`.
- La Function App marca `cold_start=true` en `customDimensions` en la primera invocación de cada instancia, y `retries` en cada request (columna de `ops.infra_requests`).
- Model Serving: inference tables del AI Gateway en `prescore-lgbm` → `hackathon.ops`; ia-ml deriva `ops.ml_inference`.
- Regla de data export de Log Analytics (tabla `AppRequests`) → ADLS `ops-export` → job serverless → `ops.infra_requests`.
- Alertas SQL de Databricks sobre `ops.*` con los umbrales de `contracts/ops.yaml`.
- Costo: presupuesto de Azure + consulta diaria a `system.billing.usage`.

### CI/CD
| Workflow | Disparo | Qué hace |
| --- | --- | --- |
| `infra.yml` | PR y push a `main` en `infra/**` | PR: backend, `init`, `validate`, `plan`, comentario en el PR. `main`: `apply` tras aprobar el environment `hackathon` |
| `data-landing.yml` | cada 6 h (cron `17 */6 * * *`) y manual; sin aprobación (solo lee S3 y escribe en `landing`) | `azcopy` S3 → `adlsagentbankdev/landing/factored-datathon/data/`, incremental (`ifSourceNewer`); sube `_manifest/manifest-<fecha>.json` con inventario (archivos, bytes, MD5) y diferencias contra la corrida anterior (nuevos, cambiados). Carga inicial 2026-09-30: 7.671 archivos, 5,35 GB, 0 fallas |
| `ci.yml` (pendiente) | PR | pytest, eval-harness (cuando exista M7), gitleaks |
| `deploy.yml` (pendiente) | push a `main` | deploy de la Function App y de la Static Web App (el token de deploy se pide con `az staticwebapp secrets list`), smoke `/chat` (N8) |
| `bundles.yml` (pendiente) | push a `main` con cambios en bundles | `databricks bundle deploy` (X2), con `run_as` = `sp-pipelines` |
| `adr-impact.yml`, `diagram-sync.yml` | PR | `diagram-sync` sube los PNG a la rama del PR y no corre en commits del bot |

Autenticación (temporal): SP `sp-deploy-iac-hackathon` con secreto `AZURE_CLIENT_SECRET` en GitHub; `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` como variables. Riesgo: cualquier rama del repo puede leer el secreto desde un workflow; se acepta por días entre tres personas. Destino: OIDC con credenciales federadas para `repo:NicolleMayol/factored-hackathon-2026-the-trident:pull_request` y `…:environment:hackathon`. Solo Nicolle aprueba el apply y mergea a `main`.

### Capacidad y límites conocidos
| Límite | Valor | Efecto |
| --- | --- | --- |
| Arranque de la Function App | 30 s, fijo | si `agent/` carga modelos al importar, la app no arranca |
| Memoria por instancia | 512 / 2048 / 4096 MB | se usa 2048 |
| Cosmos | 400 RU/s por contenedor | picos de carga de chunks deben ir con throttle |
| Cuota de App Service B1 en la suscripción | 0 | el chat va en Static Web Apps, que no usa esa cuota |
| Static Web Apps Free | 100 GB/mes de ancho de banda, 250 MB por app (a verificar) | suficiente para el chat |
| SQL Warehouse serverless apagado | varios segundos de arranque (a medir) | la primera consulta de `get_customer_profile` puede pasar los 8 s y escalar. Propuesta abierta: copiar los datos de cliente que usa el agente a Cosmos |
| Primer apply de la Function App | bug de azurerm 5.1: el bloque CORS depende de la URL de la Static Web App y falla la primera vez | volver a correr el apply; desde entonces planea bien |
| FM APIs pay-per-token | límites por workspace | se miden en N7 |
| Metastore | el workspace no lo trajo asignado; la cuenta admite uno por región | Terraform asigna el existente (`metastore_azure_eastus2`); el SP del pipeline es account admin |
| Lectura de S3 desde Azure Databricks serverless | Unity Catalog en Azure no toma llaves de S3 y serverless no deja ponerlas en la config de Spark | resuelto: copia S3 → ADLS `landing` (workflow `data-landing`); Auto Loader lee `abfss://landing@adlsagentbankdev.dfs.core.windows.net/factored-datathon/data/` |

Carga (N7): k6 desde GitHub Actions con 10/25/50 usuarios; p50/p95 en caliente, cold start aparte, error rate, costo por caso.

### Fases
| Fase | Fecha | Qué | Desbloquea |
| --- | --- | --- | --- |
| 0 · Chequeos | mar 29 noche | créditos en Cost Management, regiones de Flex, cuota de vCPU | — |
| 1 · Databricks | hecho mié 30 (22:00) | workspace, ADLS, Access Connector, storage credential, KV + scope, catálogo, esquemas, grants del equipo, `sp-agent-ro`, `sp-pipelines`, `wh-agent`, experimento | X1 → Eladio, Manuela |
| 2 · Azure app | mar 29 noche: hecho salvo `/session` | Cosmos, Function App, App Insights, `/session` | N3, N4, N2 |
| 3 · CI/CD + frontend | mié 30 | workflow `infra` (hecho), `ci.yml`, `deploy.yml`, bundles, Static Web App (creada) | N1, X2, N5 → Integración 1 |
| 4 · Observar + carga | jue 1 → sáb 3 | export a `ops.infra_requests`, smoke, tablero, k6 | N6, N8, X3, N7 |
| 5 · Ventana de jurado | sáb 3 → resultados | always-ready 1 en la Function App; Model Serving sin scale-to-zero | demo sin cold start |
| 6 · Cierre | tras resultados | `terraform destroy` | corta el gasto |

### Costo (estimación por 7 días, no cotización)
| Recurso | Supuesto | USD |
| --- | --- | --- |
| Cosmos | 200 RU/s sobre el free tier × 168 h | ≈ 2,7 |
| Function App always-ready | 1 instancia × 2 GB × 72 h (ventana de jurado) | ≈ 2 |
| Function App on-demand | dentro de la cuota mensual sin costo | ≈ 0 |
| Storage, Key Vault, Log Analytics | < 5 GB de logs | < 1 |
| Static Web Apps | Free | 0 |
| **Azure, subtotal** | | **≈ 5–6** |
| Databricks (serverless SQL, jobs, Model Serving, tokens de FM APIs) | se mide a diario en `system.billing.usage` | a medir |

Créditos disponibles: sin confirmar. `budget_usd` se fija en la fase 0. El workspace usa el SKU `trial` del diagrama DEMO: DBU Premium sin costo por 14 días desde su creación (vence cerca del 13 oct). Serverless funciona en el trial (Premium + Unity Catalog + `eastus2`). Microsoft no documenta si el trial cubre esas DBUs: se mide en `system.billing.usage` desde la primera corrida. Después del vencimiento hay que pasar el workspace a Premium a mano.

| Alternativas descartadas | Por qué |
| --- | --- |
| Bicep | no cubre Databricks (grants, SP, scope, experimento); quedaría en scripts |
| Scripts `az` | no se repiten igual; sin plan ni drift |
| Cada rol crea sus recursos | tres formas de crear infra; permisos repartidos; sin un solo `destroy` |
| App Service F1 para el chat | se detiene tras 60 min de CPU al día; riesgo durante la evaluación |
| Web App B1 + BFF (diagrama DEMO) | cuota de App Service B1 en 0; con JWT de prueba el BFF no protege nada extra; ~USD 13/mes |
| App registration propia para OIDC | exige permisos de Entra ID que hoy no hay; se usa el SP entregado por Eladio |
| Scope `fh26` respaldado en Key Vault | exige token de usuario; Terraform corre solo en el pipeline |
| `infra/bootstrap` corrido desde una laptop | Terraform corre solo en el pipeline; el backend lo crea un script idempotente |
| Cosmos con throughput compartido de 1.000 RU/s | no admite búsqueda vectorial |
| Cómputo clásico en Databricks | VMs a cargo de la suscripción (el trial solo cubre DBUs), clusters y políticas que administrar, minutos de arranque; la razón que lo pedía (llaves de S3) ya no existe |
| East US | East US 2 tiene Flex Consumption, FM APIs pay-per-token y Claude Sonnet 5 |

**Impacto.**

| Elemento | Estado | Owner | Consumers afectados | Qué deben hacer | Fecha límite |
| --- | --- | --- | --- | --- | --- |
| `infra.databricks_access` | cambia: owner datos → servicio; X1 lo entrega servicio; + esquemas `bronze`/`silver`, grants del equipo, `sp-pipelines` | servicio | datos, ia-ml | Eladio: crear tablas y pipelines en sus esquemas; elegir cómo leer S3 desde serverless. Manuela: registrar modelos en `ml` | mié 30 mañana |
| `infra.databricks_workspace` | nuevo | servicio | datos, ia-ml | usar solo serverless | mar 29 noche |
| `infra.adls` | cambia: owner datos → servicio | servicio | datos, ia-ml | nada | — |
| `infra.key_vault` | cambia: sin llaves de S3 (solo en GitHub); scope `fh26` administrado por Databricks, solo `cosmos-key` | servicio | datos, ia-ml | Eladio: no leer S3 desde Databricks; leer de ADLS `landing` | mié 30 |
| `infra.adls` | cambia: + contenedor `landing` con la copia del dataset y `_manifest/` | servicio | datos, ia-ml | Eladio: Auto Loader desde `landing`; actualizar `data.ingest_s3` en `gold.yaml` | mié 30 |
| `infra.cosmos` | cambia: 3 × 400 RU/s dedicados, vector search | servicio | ia-ml, datos | Eladio: carga del JSONL con throttle | mar 29 |
| `infra.function_app` | cambia: 2048 MB, máx. 10 instancias, arranque ≤ 30 s | servicio | ia-ml | Manuela: no cargar modelos al importar `agent/`; decir dónde corre el embedding de la consulta | mié 30 mañana |
| `infra.function_app_settings` | cambia: + `APPLICATIONINSIGHTS_CONNECTION_STRING`; secretos como referencias a Key Vault | servicio | ia-ml | nada en código | mié 30 mañana |
| `infra.identity` | cambia: ADR-12 cerrada, mock JWT HS256; triggers HTTP anónimos + validación del JWT en código; scope de agente humano en `/handoff` y `/trace` | servicio | ia-ml | Manuela: validar HS256 y `exp`; `auth_level=ANONYMOUS`; definir el scope de agente humano en `api.yaml` | mié 30 |
| `infra.app_service` | cambia: App Service F1 → Static Web Apps Free (`swa-agent-bank-dev`), llamada directa a la Function App con CORS | servicio | ia-ml | nada en infra; ver `infra.identity` | mié 30 |
| `infra.model_serving` | cambia: owner ia-ml → servicio (endpoint); el modelo sigue en `ml.prescore_lgbm` | servicio | ia-ml | Manuela: registrar la versión en UC | jue 1 |
| `infra.fm_apis` | cambia: owner ia-ml → servicio (endpoints, rate limits); el modelo sigue en ADR-02 | servicio | ia-ml | nada | — |
| `infra.ci_cd` | cambia: workflow `infra` con SP y secreto temporal (OIDC pendiente), environment `hackathon` con aprobación | servicio | datos, ia-ml | nada | hecho |
| `infra.iac` | nuevo | servicio | datos, ia-ml | pedir recursos por PR a `infra/` | — |

**Cómo se prueba.**

| Prueba | Umbral | Dónde se registra |
| --- | --- | --- |
| `terraform plan` tras `apply` | 0 cambios | CI |
| Secretos en el repo | 0 hallazgos | CI (gitleaks) |
| App Settings con secretos en claro | 0; todos son referencias a Key Vault | CI (`az functionapp config appsettings list`) |
| Permisos de `sp-agent-ro` | `SELECT` en gold/ref pasa; `INSERT` falla | CI (test SQL) |
| `/healthz` tras deploy | 200 con 4 dependencias en ok | CI (N8) |
| Arranque de la Function App | < 30 s; cold start p50/p95 aparte | `ops.infra_requests.cold_start` |
| TTL de `conversations` | documento borrado a las 24 h | test en CI |
| Carga 10/25/50 usuarios | p95 en caliente ≤ 8 s, error rate ≤ 2 % | k6 → `ops.infra_requests` (N7) |
| Trazas | 100 % de requests con `operation_id` = `trace_id` | `ops.infra_requests` ⋈ `ops.agent_turns` |
| Presupuesto | alerta al 50 % llega por correo | Cost Management |

**Hackathon vs To-Be.**

| Hackathon | To-Be |
| --- | --- |
| Un entorno | dev/staging/prod con promoción |
| SP de CI con secreto en GitHub (Contributor + RBAC Administrator en la suscripción) | OIDC; SPs separados para plan y apply |
| Mock JWT HS256 | Entra External ID |
| `COSMOS_KEY` en Key Vault | RBAC de Cosmos con identidad administrada, sin llave |
| Static Web App y Function App con endpoints públicos; chat sin BFF | página ENTERPRISE de `diagrams/arquitectura.drawio`: App Service + Easy Auth + token OBO detrás de WAF y firewall, private endpoints y DNS privado, Sentinel |
| Function App con llave del storage | identidad administrada sobre el storage |
| Always-ready solo en ventana de jurado | always-ready permanente o plan Premium |
| Model Serving scale-to-zero | provisioned throughput |
| Data export de Log Analytics → ADLS | diagnostic settings → Event Hubs → streaming |
| Una región | multi-región y retención por país |

**Dependencias.**

| # | Entregable | De → para | Formato | Fecha | Mock |
| --- | --- | --- | --- | --- | --- |
| X1 (cambia) | Workspace Premium trial, ADLS, storage credential, KV + scope `fh26`, catálogo y esquemas (`bronze`, `silver`, `gold`, `ref`, `ops`, `ml`), grants del equipo, `sp-agent-ro`, `sp-pipelines`, `wh-agent`, experimento con `CAN_EDIT` | Nicolle → Eladio, Manuela | Terraform `infra/databricks` + URL y http path | mar 29 noche; grants mié 30 mañana | CSV local; experimento personal |
| N1 (cambia) | Repo en `NicolleMayol/factored-hackathon-2026-the-trident`; workflow `infra` (plan en PR, apply con aprobación); OIDC y gitleaks pendientes | Nicolle → todos | GitHub | hecho (OIDC pendiente) | — |
| N2 (cambia) | Function App Flex 2048 MB + App Settings de `infra.yaml` v3 | Nicolle → Manuela | Azure | mié 30 mañana | `func start` + `local.settings.json` |
| N3 (cambia) | Cosmos free tier, 3 contenedores × 400 RU/s, vector search | Nicolle → Manuela, Eladio | Azure | mar 29 | emulador / LanceDB |
| N5 (cambia) | Static Web Apps Free: chat + vista `/handoff` | Nicolle → Manuela | Azure | recurso creado; UI mié 30 | curl |

**Base regulatoria.** No aplica en el hackathon: el dataset es de Factored y todo queda en East US 2 dentro del tenant. Residencia y retención por país quedan en To-Be, a validar con legal.
