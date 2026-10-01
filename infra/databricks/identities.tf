# Service principals de Databricks. Se crean desde el workspace; con identity federation quedan
# también en la cuenta y sirven como principals de Unity Catalog.

# run_as de los Asset Bundles de datos (X2).
resource "databricks_service_principal" "pipelines" {
  display_name = "sp-pipelines"
}

# Identidad del agente (Function App): solo lectura de gold y ref. Entra con OAuth M2M; el secreto
# va a Key Vault (secrets.tf) y la Function lo lee como DATABRICKS_CLIENT_SECRET.
resource "databricks_service_principal" "agent_ro" {
  display_name = "sp-agent-ro"
}

resource "databricks_service_principal_secret" "agent_ro" {
  service_principal_id = databricks_service_principal.agent_ro.id
}

# Quién puede desplegar jobs con run_as = sp-pipelines: el SP del pipeline (bundles.yml) y datos
# (deploy manual). Autoritativo: el SP del pipeline queda también como manager para no perder control.
resource "databricks_access_control_rule_set" "pipelines" {
  name = "accounts/${var.databricks_account_id}/servicePrincipals/${local.sp_pipelines}/ruleSets/default"

  grant_rules {
    principals = ["servicePrincipals/${data.azurerm_client_config.current.client_id}"]
    role       = "roles/servicePrincipal.manager"
  }

  grant_rules {
    principals = concat(
      ["servicePrincipals/${data.azurerm_client_config.current.client_id}"],
      [for u in var.datos_users : "users/${u}"],
    )
    role = "roles/servicePrincipal.user"
  }
}

# ia-ml aún no está en el workspace: Terraform la agrega. force = true la toma si alguien ya la agregó
# a mano. Eladio no va aquí: ya existe y es admin del workspace. La persona debe existir en el
# tenant de Entra ID de la suscripción (como invitada, si es de fuera).
resource "databricks_user" "iaml" {
  for_each  = toset(var.iaml_users)
  user_name = each.key
  force     = true
}
