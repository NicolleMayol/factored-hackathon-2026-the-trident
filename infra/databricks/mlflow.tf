# Experimento del agente (ADR-18): el agente escribe trazas con sp-agent-ro; ia-ml lo administra.
resource "databricks_directory" "fh26" {
  path = "/Shared/fh26"
}

resource "databricks_mlflow_experiment" "agente" {
  name       = "${databricks_directory.fh26.path}/agente"
  depends_on = [databricks_directory.fh26]
}

resource "databricks_permissions" "experiment" {
  experiment_id = databricks_mlflow_experiment.agente.id

  access_control {
    service_principal_name = local.sp_agent
    permission_level       = "CAN_EDIT"
  }

  dynamic "access_control" {
    for_each = local.iaml
    content {
      user_name        = access_control.value
      permission_level = "CAN_MANAGE"
    }
  }
}
