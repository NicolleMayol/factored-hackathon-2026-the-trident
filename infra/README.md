# infra · Terraform (ADR-19)

Terraform corre solo en GitHub Actions (`.github/workflows/infra.yml`), nunca desde una laptop.

| Evento | Job | Qué hace |
| --- | --- | --- |
| PR que toca `infra/**` | `plan` | crea el backend si falta, `init`, `validate`, `plan`; comenta el plan en el PR |
| push a `main` | `apply` | espera la aprobación del environment `hackathon`; `apply` |

| Carpeta | Contenido |
| --- | --- |
| `azure/` | RG, Key Vault, Log Analytics + App Insights, Cosmos (3 × 400 RU/s, vector search), Function App Flex, Web App B1, Databricks workspace (trial), ADLS, Access Connector, presupuesto |
| `databricks/` | pendiente: Unity Catalog, grants, `sp-agent-ro`, `sp-pipelines`, scope `fh26`, `wh-agent`, experimento. Requiere account admin de Databricks |
| `scripts/ensure-backend.sh` | crea `rg-tfstate-agent-bank-dev` / `sttfstateagentbankdev` / `tfstate` si no existen |

Configuración en GitHub (Settings → Secrets and variables → Actions):

| Tipo | Nombre | Valor |
| --- | --- | --- |
| variable | `AZURE_CLIENT_ID` | client id de `sp-deploy-iac-hackathon` |
| variable | `AZURE_TENANT_ID` | tenant |
| variable | `AZURE_SUBSCRIPTION_ID` | `sub-ai-dev` |
| secreto | `AZURE_CLIENT_SECRET` | secreto del SP (temporal, hasta OIDC) |
| variable | `BUDGET_AMOUNT`, `BUDGET_EMAILS`, `ADMIN_OBJECT_IDS` | opcionales; listas en formato `["a","b"]` |
| secreto | `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` | opcionales; llaves del bucket de Factored |
| variable | `FUNCTION_ALWAYS_READY` | `true` solo en la ventana de jurado |
| variable | `DATABRICKS_CLIENT_ID`, `SQL_HTTP_PATH` | llegan del stack de Databricks |
