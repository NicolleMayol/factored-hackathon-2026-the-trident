resource "azurerm_key_vault" "main" {
  name                       = "kv-agent-bank-dev"
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  rbac_authorization_enabled = true
  purge_protection_enabled   = false
  soft_delete_retention_days = 7
  tags                       = local.tags
}

# La identidad que corre Terraform (el SP del pipeline) escribe secretos.
resource "azurerm_role_assignment" "kv_deployer" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "azurerm_role_assignment" "kv_admins" {
  for_each             = toset(var.admin_object_ids)
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = each.value
}

# ia-ml lee solo cosmos-key (rol sobre el secreto, no sobre el vault): para correr el agente en
# local con AGENT_STORE=real. La Function no lo necesita: lee el secreto con su identidad.
resource "azurerm_role_assignment" "kv_iaml_cosmos_key" {
  for_each             = toset(var.iaml_object_ids)
  scope                = azurerm_key_vault_secret.cosmos_key.resource_versionless_id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = each.value
}

# Los permisos de RBAC tardan en propagarse; sin esta espera el primer apply falla con 403.
resource "time_sleep" "kv_rbac" {
  depends_on      = [azurerm_role_assignment.kv_deployer]
  create_duration = "60s"
}

resource "random_password" "jwt" {
  length  = 64
  special = false
}

resource "azurerm_key_vault_secret" "jwt_signing_key" {
  name         = "jwt-signing-key"
  value        = random_password.jwt.result
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [time_sleep.kv_rbac]
}

resource "azurerm_key_vault_secret" "cosmos_key" {
  name         = "cosmos-key"
  value        = azurerm_cosmosdb_account.main.primary_key
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [time_sleep.kv_rbac]
}

# El secreto OAuth de sp-agent-ro lo crea y guarda infra/databricks como `sp-agent-ro-client-secret`.
# Este stack deja de manejar el marcador "databricks-client-secret" sin borrarlo de Key Vault.
removed {
  from = azurerm_key_vault_secret.databricks_client_secret

  lifecycle {
    destroy = false
  }
}
