# X1 · parte Databricks (ADR-19, ADR-20). Lee los recursos de infra/azure por nombre, sin remote state:
# así este stack no depende de las salidas del otro y se puede planear por separado.
data "azurerm_databricks_workspace" "main" {
  name                = "dbw-agent-bank-dev"
  resource_group_name = "rg-ai-agents-dev"
}

data "azurerm_databricks_access_connector" "main" {
  name                = "acc-agent-bank-dev"
  resource_group_name = "rg-ai-agents-dev"
}

data "azurerm_key_vault" "main" {
  name                = "kv-agent-bank-dev"
  resource_group_name = "rg-ai-agents-dev"
}

data "azurerm_key_vault_secret" "cosmos_key" {
  name         = "cosmos-key"
  key_vault_id = data.azurerm_key_vault.main.id
}

locals {
  adls    = "adlsagentbankdev"
  schemas = ["bronze", "silver", "gold", "ref", "ops", "ml"]

  # Una external location por container (ADR-20). unity-catalog es la managed location del catálogo:
  # el metastore automático no tiene storage propio, así que el catálogo necesita una.
  containers = toset(concat(local.schemas, ["landing", "unity-catalog"]))
  url        = { for c in local.containers : c => "abfss://${c}@${local.adls}.dfs.core.windows.net/" }

  sp_pipelines = databricks_service_principal.pipelines.application_id
  sp_agent     = databricks_service_principal.agent_ro.application_id
  iaml         = [for u in databricks_user.iaml : u.user_name] # depende de que exista el usuario

  # Quién escribe (datos) y quién lee (ia-ml y el agente).
  writers = concat(var.datos_users, [local.sp_pipelines])
  readers = concat(local.iaml, [local.sp_agent])
}
