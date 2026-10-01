# Pasar a variables de GitHub para infra/azure: SQL_HTTP_PATH y DATABRICKS_CLIENT_ID.
output "sql_http_path" { value = databricks_sql_endpoint.wh_agent.odbc_params[0].path }
output "sp_agent_ro_application_id" { value = databricks_service_principal.agent_ro.application_id }
output "sp_pipelines_application_id" { value = databricks_service_principal.pipelines.application_id }
output "sp_agent_ro_secret_kv" { value = azurerm_key_vault_secret.sp_agent_ro.name }
output "catalog" { value = databricks_catalog.hackathon.name }
output "external_locations" { value = sort([for l in databricks_external_location.adls : l.name]) }
