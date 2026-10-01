terraform {
  required_version = ">= 1.9"

  required_providers {
    azurerm    = { source = "hashicorp/azurerm", version = "~> 5.1" }
    databricks = { source = "databricks/databricks", version = "~> 1.135" }
  }

  # Mismo storage de estado que infra/azure, otra llave.
  backend "azurerm" {
    resource_group_name  = "rg-tfstate-agent-bank-dev"
    storage_account_name = "sttfstateagentbankdev"
    container_name       = "tfstate"
    key                  = "databricks.tfstate"
    use_azuread_auth     = true
  }
}

# Autenticación: OIDC de GitHub (ARM_USE_OIDC, ARM_CLIENT_ID, ARM_TENANT_ID, ARM_SUBSCRIPTION_ID; las pone el workflow).
provider "azurerm" {
  features {}
  resource_provider_registrations = "none"
}

# El SP del pipeline es Contributor del workspace, así que entra como workspace admin. En un workspace
# con Unity Catalog automático, el workspace admin ya tiene CREATE CATALOG, CREATE STORAGE CREDENTIAL
# y CREATE EXTERNAL LOCATION sobre el metastore.
provider "databricks" {
  host                        = "https://${data.azurerm_databricks_workspace.main.workspace_url}"
  azure_workspace_resource_id = data.azurerm_databricks_workspace.main.id
  auth_type                   = "github-oidc-azure" # ARM_CLIENT_ID y ARM_TENANT_ID del workflow
}

# Nivel cuenta: metastore y su asignación al workspace. El SP del pipeline debe ser account admin
# (lo asigna una vez un account admin en accounts.azuredatabricks.net).
provider "databricks" {
  alias      = "account"
  host       = "https://accounts.azuredatabricks.net"
  account_id = var.databricks_account_id
  auth_type  = "github-oidc-azure"
}
