# ADR-19 · nombres del diagrama DEMO (diagrams/arquitectura.drawio)
locals {
  tags = {
    project    = "fh26-agente-credito"
    owner      = "servicio"
    managed_by = "terraform"
  }
}

data "azurerm_client_config" "current" {}

resource "azurerm_resource_group" "main" {
  name     = "rg-ai-agents-dev"
  location = var.location
  tags     = local.tags
}
