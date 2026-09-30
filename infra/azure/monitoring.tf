resource "azurerm_log_analytics_workspace" "main" {
  name                = "log-analytics-agent-bank-dev"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = local.tags
}

resource "azurerm_application_insights" "main" {
  name                = "app-insight-agent-bank-dev"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  application_type    = "web"
  workspace_id        = azurerm_log_analytics_workspace.main.id
  tags                = local.tags
}

resource "azurerm_consumption_budget_resource_group" "main" {
  count             = length(var.budget_emails) > 0 ? 1 : 0
  name              = "budget-agent-bank-dev"
  resource_group_id = azurerm_resource_group.main.id
  amount            = var.budget_amount
  time_grain        = "Monthly"

  time_period {
    start_date = formatdate("YYYY-MM-01'T'00:00:00Z", timestamp()) # Azure exige el día 1 del mes en curso
  }

  lifecycle {
    ignore_changes = [time_period] # si no, timestamp() cambia en cada plan
  }

  dynamic "notification" {
    for_each = [50, 80, 100]
    content {
      enabled        = true
      threshold      = notification.value
      operator       = "GreaterThanOrEqualTo"
      threshold_type = "Actual"
      contact_emails = var.budget_emails
    }
  }
}
