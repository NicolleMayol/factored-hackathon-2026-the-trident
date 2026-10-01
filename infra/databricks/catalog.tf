# Catálogo hackathon con un esquema por capa; cada esquema guarda sus tablas en su propio container (ADR-20).
resource "databricks_catalog" "hackathon" {
  name           = "hackathon"
  storage_root   = "${local.url["unity-catalog"]}hackathon"
  isolation_mode = "ISOLATED"
  comment        = "Agente Crédito LATAM · Terraform (ADR-19)"
  depends_on     = [databricks_external_location.adls]
}

resource "databricks_schema" "this" {
  for_each     = toset(local.schemas)
  catalog_name = databricks_catalog.hackathon.name
  name         = each.key
  storage_root = local.url[local.container_of[each.key]]
  comment      = "Terraform (ADR-20)"
  depends_on   = [databricks_external_location.adls]
}

# Insumos que no van al repo (ADR-20). La escritura sale de los grants de ref.
resource "databricks_volume" "ref" {
  for_each     = toset(["policy_docs", "fuentes"]) # policy_docs: E7 · fuentes: snapshots de ref (E6)
  catalog_name = databricks_catalog.hackathon.name
  schema_name  = databricks_schema.this["ref"].name
  name         = each.key
  volume_type  = "MANAGED"
  comment      = "Terraform (ADR-20)"
}

# ---- Grants (contracts/infra.yaml · databricks_access) ----
resource "databricks_grants" "catalog" {
  catalog = databricks_catalog.hackathon.id

  dynamic "grant" {
    for_each = concat(local.writers, local.readers)
    content {
      principal  = grant.value
      privileges = ["USE_CATALOG"]
    }
  }
}

locals {
  # datos y sp-pipelines: ALL PRIVILEGES en bronze, silver, gold, ref, ops; nada en ml (ADR-20).
  # ia-ml y sp-agent-ro: lectura de gold y ref. ia-ml: ALL PRIVILEGES en ml; en ops crea sus
  # tablas (agent_turns, ml_inference) y queda como dueña de ellas.
  schema_grants = {
    for s in local.schemas : s => tolist(concat(
      s != "ml" ? [for p in local.writers : { principal = p, privileges = tolist(["ALL_PRIVILEGES"]) }] : [],
      contains(["gold", "ref"], s) ? [for p in local.readers : { principal = p, privileges = tolist(["USE_SCHEMA", "SELECT"]) }] : [],
      s == "ops" ? [for p in local.iaml : { principal = p, privileges = tolist(["USE_SCHEMA", "SELECT", "CREATE_TABLE"]) }] : [],
      s == "ml" ? [for p in local.iaml : { principal = p, privileges = tolist(["ALL_PRIVILEGES"]) }] : [],
    ))
  }
}

resource "databricks_grants" "schema" {
  for_each = { for s, g in local.schema_grants : s => g if length(g) > 0 }
  schema   = databricks_schema.this[each.key].id

  dynamic "grant" {
    for_each = each.value
    content {
      principal  = grant.value.principal
      privileges = grant.value.privileges
    }
  }
}
