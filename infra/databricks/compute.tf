# wh-agent: serverless 2X-Small, auto-stop 10 min (contracts/infra.yaml).
resource "databricks_sql_endpoint" "wh_agent" {
  name                      = "wh-agent"
  cluster_size              = "2X-Small"
  min_num_clusters          = 1
  max_num_clusters          = 1
  auto_stop_mins            = 10
  enable_serverless_compute = true
  warehouse_type            = "PRO"
  no_wait                   = true
}

resource "databricks_permissions" "wh_agent" {
  sql_endpoint_id = databricks_sql_endpoint.wh_agent.id

  dynamic "access_control" {
    for_each = concat(var.datos_users, local.iaml)
    content {
      user_name        = access_control.value
      permission_level = "CAN_USE"
    }
  }

  dynamic "access_control" {
    for_each = [local.sp_pipelines, local.sp_agent]
    content {
      service_principal_name = access_control.value
      permission_level       = "CAN_USE"
    }
  }
}
