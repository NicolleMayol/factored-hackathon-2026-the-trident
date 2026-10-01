# Scope fh26 administrado por Databricks. Terraform copia el valor desde Key Vault (ADR-19).
resource "databricks_secret_scope" "fh26" {
  name = "fh26"
}

resource "databricks_secret" "cosmos_key" {
  scope        = databricks_secret_scope.fh26.name
  key          = "cosmos-key"
  string_value = data.azurerm_key_vault_secret.cosmos_key.value
}

# E7 carga el JSONL de chunks a Cosmos con sp-pipelines (ADR-20).
resource "databricks_secret_acl" "pipelines_read" {
  scope      = databricks_secret_scope.fh26.name
  principal  = local.sp_pipelines
  permission = "READ"
}
