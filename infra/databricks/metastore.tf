# Metastore de Unity Catalog en eastus2 y su asignación al workspace (el workspace no trajo uno).
# Sin storage propio: cada catálogo declara su managed location.
data "azurerm_client_config" "current" {}

resource "databricks_metastore" "eastus2" {
  count    = var.existing_metastore_id == "" ? 1 : 0
  provider = databricks.account
  name     = "metastore-eastus2"
  region   = "eastus2"
  # Owner: el SP del pipeline, que lo crea. Queda como metastore admin; Nicolle es account admin.
}

locals {
  metastore_id = coalesce(var.existing_metastore_id, one(databricks_metastore.eastus2[*].id))
}

resource "databricks_metastore_assignment" "this" {
  provider     = databricks.account
  metastore_id = local.metastore_id
  workspace_id = data.azurerm_databricks_workspace.main.workspace_id
}

# Solo si el metastore ya existía y el SP no es su dueño. No es autoritativo: no toca otros grants.
resource "databricks_grant" "metastore_sp" {
  count      = var.existing_metastore_id == "" ? 0 : 1
  metastore  = local.metastore_id
  principal  = data.azurerm_client_config.current.client_id
  privileges = ["CREATE_CATALOG", "CREATE_EXTERNAL_LOCATION", "CREATE_STORAGE_CREDENTIAL"]
  depends_on = [databricks_metastore_assignment.this]
}
