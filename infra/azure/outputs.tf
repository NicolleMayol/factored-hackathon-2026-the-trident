output "resource_group" { value = azurerm_resource_group.main.name }
output "key_vault_uri" { value = azurerm_key_vault.main.vault_uri }
output "cosmos_endpoint" { value = azurerm_cosmosdb_account.main.endpoint }
output "function_app_name" { value = azurerm_function_app_flex_consumption.main.name }
output "chat_url" { value = "https://${azurerm_static_web_app.main.default_host_name}" }
output "databricks_workspace_url" { value = "https://${azurerm_databricks_workspace.main.workspace_url}" }
output "adls_account" { value = azurerm_storage_account.adls.name }
output "access_connector_id" { value = azurerm_databricks_access_connector.main.id }
