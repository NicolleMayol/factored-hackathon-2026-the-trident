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
  kv_ref = { for k, uri in {
    DATABRICKS_CLIENT_SECRET = "${azurerm_key_vault.main.vault_uri}secrets/sp-agent-ro-client-secret" # lo escribe infra/databricks
    COSMOS_KEY               = azurerm_key_vault_secret.cosmos_key.versionless_id
    JWT_SIGNING_KEY          = azurerm_key_vault_secret.jwt_signing_key.versionless_id
  } : k => "@Microsoft.KeyVault(SecretUri=${uri})" }
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

    cors {
      allowed_origins = ["https://${azurerm_static_web_app.main.default_host_name}"]
    }
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
    # ADR-21: mock o real por dependencia. El paquete es de solo lectura en Flex; los adaptadores
    # locales escriben en AGENT_MOCK_DIR (deploy/function/function_app.py copia data/mock ahí).
    AGENT_MOCK_DIR = "/tmp/fh26-mock"
  }, { for k, v in var.agent_modes : "AGENT_${upper(k)}" => v })
}

resource "azurerm_role_assignment" "func_kv" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_function_app_flex_consumption.main.identity[0].principal_id
}

# ------------------------------------------------------------------ Chat UI (N5)
# Static Web Apps Free en vez de Web App B1: sin costo, sin cuota de App Service (que está en 0),
# y la página carga desde CDN aunque la Function esté fría. Con el JWT de prueba (ADR-12) un BFF
# no protege nada extra; App Service + Easy Auth queda en ENTERPRISE (To-Be).
# El token de deploy no se guarda: el workflow lo lee con `az staticwebapp secrets list`.
resource "azurerm_static_web_app" "main" {
  name                = "swa-agent-bank-dev"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku_tier            = "Free"
  sku_size            = "Free"
  tags                = local.tags

  # deploy-web sube la UI con Azure/static-web-apps-deploy y Azure anota en el recurso el repo y la
  # rama de origen. No los maneja Terraform: sin esto cada plan los quiere poner en null (drift).
  lifecycle {
    ignore_changes = [repository_url, repository_branch]
  }
}
