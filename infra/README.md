# infra · Terraform (ADR-19)

Terraform corre solo en GitHub Actions (`.github/workflows/infra.yml`), nunca desde una laptop.

| Evento | Job | Qué hace |
| --- | --- | --- |
| PR que toca `infra/**` | `plan` | crea el backend si falta; `init`, `validate`, `plan` de `azure` y luego de `databricks`; comenta los dos planes en el PR |
| push a `main` | `apply` | espera la aprobación del environment `hackathon`; `apply` de `azure` y luego de `databricks` |

| Carpeta | Contenido |
| --- | --- |
| `azure/` | RG, Key Vault, Log Analytics + App Insights, Cosmos (3 × 400 RU/s, vector search), Function App Flex, Static Web App Free, Databricks workspace (trial), ADLS, Access Connector, presupuesto |
| `databricks/` | storage credential, external locations, catálogo `hackathon`, esquemas, volúmenes, grants por esquema, `sp-agent-ro`, `sp-pipelines`, scope `fh26`, `wh-agent`, experimento `/Shared/fh26/agente` |
| `scripts/ensure-backend.sh` | crea `rg-tfstate-agent-bank-dev` / `sttfstateagentbankdev` / `tfstate` si no existen |

Configuración en GitHub (Settings → Secrets and variables → Actions):

| Tipo | Nombre | Valor |
| --- | --- | --- |
| variable | `AZURE_CLIENT_ID` | client id de `sp-deploy-iac-hackathon` |
| variable | `AZURE_TENANT_ID` | tenant |
| variable | `AZURE_SUBSCRIPTION_ID` | `sub-ai-dev` |
| variable | `BUDGET_AMOUNT`, `BUDGET_EMAILS`, `ADMIN_OBJECT_IDS` | opcionales; listas en formato `["a","b"]` |
| secreto | `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` | opcionales; llaves del bucket de Factored |
| variable | `FUNCTION_ALWAYS_READY` | `true` solo en la ventana de jurado |
| variable | `DATABRICKS_CLIENT_ID`, `SQL_HTTP_PATH` | salidas del stack de Databricks (`sp_agent_ro_application_id`, `sql_http_path`) |
| variable | `DATABRICKS_HOST` | URL del workspace, para `bundles.yml` |
| variable | `BUNDLE_TARGET` | opcional: target que despliega `bundles.yml` en `main` (por defecto `prod`) |
| variable | `DATABRICKS_ACCOUNT_ID` | ID de la cuenta de Databricks; el SP del pipeline debe ser account admin |
| variable | `DATABRICKS_METASTORE_ID` | opcional: solo si ya hay un metastore en eastus2; si falta, Terraform crea `metastore-eastus2` |
| variable | `DATOS_USERS`, `IAML_USERS` | correos de Databricks de cada rol, formato `["a@b.com"]`; cada persona debe existir ya en el workspace |

## Asset Bundles de datos (X2)

`bundles.yml` busca cada `databricks.yml` dentro de `data/`: en un PR corre `validate`, y en `main`, `deploy -t prod`. El target `prod` debe correr como `sp-pipelines`:

```yaml
targets:
  dev:
    mode: development
    default: true
  prod:
    mode: production
    run_as:
      service_principal_name: 0bad9ec7-e458-4fe0-8043-50b7847dd194 # sp-pipelines
    permissions:
      - user_name: <tu usuario de Databricks>
        level: CAN_MANAGE
```

Grants de `sp-pipelines`: `ALL PRIVILEGES` en `bronze`…`ops`, `READ FILES` en `landing`, `READ` en el scope `fh26`, `CAN_USE` en `wh-agent`.

## OIDC (sin secreto de Azure en GitHub)

El SP `sp-deploy-iac-hackathon` tiene tres credenciales federadas, creadas una vez con `az` por Nicolle (Cloud Application Administrator):

| Nombre | Sujeto | Quién lo usa |
| --- | --- | --- |
| `gh-pull-request` | `repo:NicolleMayol@42590549/factored-hackathon-2026-the-trident@1396845609:pull_request` | plan de `infra`, `validate` de `bundles` |
| `gh-env-hackathon` | `repo:NicolleMayol@42590549/factored-hackathon-2026-the-trident@1396845609:environment:hackathon` | apply de `infra` |
| `gh-main` | `repo:NicolleMayol@42590549/factored-hackathon-2026-the-trident@1396845609:ref:refs/heads/main` | `bundles` y `data-landing` en `main` |

GitHub manda el sujeto con los IDs de dueño y repo (`dueño@id/repo@id`), así que un repo renombrado no puede hacerse pasar por este. Cada workflow pide `id-token: write`. Terraform usa `ARM_USE_OIDC`; el provider de Databricks y el CLI, `github-oidc-azure`; `azcopy`, la sesión de `azure/login`.
