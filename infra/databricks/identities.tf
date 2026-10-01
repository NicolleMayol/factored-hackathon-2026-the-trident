# Service principals de Databricks. Se crean desde el workspace; con identity federation quedan
# también en la cuenta y sirven como principals de Unity Catalog.

# run_as de los Asset Bundles de datos (X2).
resource "databricks_service_principal" "pipelines" {
  display_name = "sp-pipelines"
}

# Identidad del agente (Function App): solo lectura de gold y ref. El secreto OAuth M2M y su paso a
# Key Vault van en el siguiente PR (Function App).
resource "databricks_service_principal" "agent_ro" {
  display_name = "sp-agent-ro"
}

# ia-ml aún no está en el workspace: Terraform la agrega. force = true la toma si alguien ya la agregó
# a mano. Eladio no va aquí: ya existe y es admin del workspace. La persona debe existir en el
# tenant de Entra ID de la suscripción (como invitada, si es de fuera).
resource "databricks_user" "iaml" {
  for_each  = toset(var.iaml_users)
  user_name = each.key
  force     = true
}
