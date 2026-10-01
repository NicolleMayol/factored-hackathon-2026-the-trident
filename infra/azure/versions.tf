terraform {
  required_version = ">= 1.9"

  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "~> 5.1" }
    azapi   = { source = "azure/azapi", version = "~> 2.0" }
    random  = { source = "hashicorp/random", version = "~> 3.6" }
    time    = { source = "hashicorp/time", version = "~> 0.12" }
  }

  # El storage del estado lo crea infra/scripts/ensure-backend.sh antes de `terraform init`.
  backend "azurerm" {
    resource_group_name  = "rg-tfstate-agent-bank-dev"
    storage_account_name = "sttfstateagentbankdev"
    container_name       = "tfstate"
    key                  = "azure.tfstate"
    use_azuread_auth     = true
  }
}

# Autenticación: OIDC de GitHub (ARM_USE_OIDC, ARM_CLIENT_ID, ARM_TENANT_ID, ARM_SUBSCRIPTION_ID; las pone el workflow).
provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy = true # hackathon: `terraform destroy` libera el nombre del Key Vault
    }
  }
  resource_provider_registrations = "none" # ya registrados a mano el 2026-09-29
}

provider "azapi" {}
