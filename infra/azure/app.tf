# ------------------------------------------------------------------ Function App (ADR-18)
resource "azurerm_storage_account" "func" {
  name                            = "stfuncagentbankdev"
  location                        = azurerm_resource_group.main.location
  resource_group_name             = azurerm_resource_group.main.name
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
  tags                            = local.tags
}

resource "azurerm_storage_container" "func_deploy" {
  name                  = "deploy"
  storage_account_id    = azurerm_storage_account.func.id
  container_access_type = "private"
}

resource "azurerm_service_plan" "func" {
  name                = "asp-func-agent-bank-dev"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  os_type             = "Linux"
  sku_name            = "FC1"
  tags                = local.tags
}

locals {
  kv_ref = { for k, s in {
    DATABRICKS_CLIENT_SECRET = azurerm_key_vault_secret.databricks_client_secret
    COSMOS_KEY               = azurerm_key_vault_secret.cosmos_key
    JWT_SIGNING_KEY          = azurerm_key_vault_secret.jwt_signing_key
  } : k => "@Microsoft.KeyVault(SecretUri=${s.versionless_id})" }
}

resource "azurerm_function_app_flex_consumption" "main" {
  name                = "func-agent-bank-dev"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  service_plan_id     = azurerm_service_plan.func.id
  https_only          = true
  tags                = local.tags

  runtime_name           = "python"
  runtime_version        = "3.11"
  instance_memory_in_mb  = 2048
  maximum_instance_count = 10

  storage_container_type      = "blobContainer"
  storage_container_endpoint  = "${azurerm_storage_account.func.primary_blob_endpoint}${azurerm_storage_container.func_deploy.name}"
  storage_authentication_type = "StorageAccountConnectionString"
  storage_access_key          = azurerm_storage_account.func.primary_access_key

  dynamic "always_ready" {
    for_each = var.function_always_ready ? [1] : []
    content {
      name           = "http"
      instance_count = 1
    }
  }

  identity {
    type = "SystemAssigned"
  }

  site_config {
    application_insights_connection_string = azurerm_application_insights.main.connection_string
  }

  # contracts/infra.yaml v3 · function_app.app_settings
  app_settings = merge(local.kv_ref, {
    DATABRICKS_HOST      = "https://${azurerm_databricks_workspace.main.workspace_url}"
    DATABRICKS_CLIENT_ID = var.databricks_client_id
    SQL_HTTP_PATH        = var.sql_http_path
    FM_ENDPOINT_MAIN     = var.fm_endpoint_main
    FM_ENDPOINT_SMALL    = var.fm_endpoint_small
    PRESCORE_ENDPOINT    = "prescore-lgbm"
    COSMOS_ENDPOINT      = azurerm_cosmosdb_account.main.endpoint
    MLFLOW_TRACKING_URI  = "databricks"
    MLFLOW_EXPERIMENT    = "/Shared/fh26/agente"
  })
}

resource "azurerm_role_assignment" "func_kv" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_function_app_flex_consumption.main.identity[0].principal_id
}

# ------------------------------------------------------------------ Web App (UI + BFF, N5)
resource "azurerm_service_plan" "web" {
  name                = "asp-agent-bank-dev"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  os_type             = "Linux"
  sku_name            = "B1"
  tags                = local.tags
}

resource "azurerm_linux_web_app" "main" {
  name                = "wapp-agent-bank-dev"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  service_plan_id     = azurerm_service_plan.web.id
  https_only          = true
  tags                = local.tags

  identity {
    type = "SystemAssigned"
  }

  site_config {
    always_on  = true
    ftps_state = "Disabled"
    application_stack {
      python_version = "3.11"
    }
  }

  # App Settings del BFF: se definen en N5.
  app_settings = {
    APPLICATIONINSIGHTS_CONNECTION_STRING = azurerm_application_insights.main.connection_string
  }
}
