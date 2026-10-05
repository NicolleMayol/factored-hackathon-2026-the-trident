# X1 · parte Azure. Unity Catalog, grants, SPs y scope van en infra/databricks.
resource "azurerm_databricks_workspace" "main" {
  name                        = "dbw-agent-bank-dev"
  location                    = azurerm_resource_group.main.location
  resource_group_name         = azurerm_resource_group.main.name
  sku                         = "premium" # ADR-19 v3.7: el trial no trae Model Serving (FEATURE_DISABLED); cambio en el lugar
  managed_resource_group_name = "rg-ai-agents-dev-dbw-managed"
  tags                        = local.tags
}

resource "azurerm_storage_account" "adls" {
  name                            = "adlsagentbankdev"
  location                        = azurerm_resource_group.main.location
  resource_group_name             = azurerm_resource_group.main.name
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  account_kind                    = "StorageV2"
  is_hns_enabled                  = true
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
  tags                            = local.tags
}

resource "azurerm_storage_container" "adls" {
  # landing: copia de S3 (workflow data-landing). bronze…ml-data: managed location de cada esquema (ADR-20).
  # El esquema ml usa "ml-data": Azure pide nombres de container de 3 a 63 caracteres.
  for_each              = toset(["unity-catalog", "ops-export", "landing", "bronze", "silver", "gold", "ref", "ops", "ml-data"])
  name                  = each.value
  storage_account_id    = azurerm_storage_account.adls.id
  container_access_type = "private"
}

resource "azurerm_databricks_access_connector" "main" {
  name                = "acc-agent-bank-dev"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.tags

  identity {
    type = "SystemAssigned"
  }
}

resource "azurerm_role_assignment" "access_connector_adls" {
  scope                = azurerm_storage_account.adls.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_databricks_access_connector.main.identity[0].principal_id
}
