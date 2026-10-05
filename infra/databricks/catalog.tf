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

  # servicio: ve y administra todo el catálogo (el dueño es el SP del pipeline).
  dynamic "grant" {
    for_each = var.admin_users
    content {
      principal  = grant.value
      privileges = ["ALL_PRIVILEGES", "MANAGE"]
    }
  }

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
  # tablas (agent_turns, ml_inference) y queda como dueña de ellas. En silver, ia-ml solo entra al
  # esquema (USE_SCHEMA); el SELECT va tabla por tabla (abajo), no sobre todo el esquema.
  schema_grants = {
    for s in local.schemas : s => tolist(concat(
      s != "ml" ? [for p in local.writers : { principal = p, privileges = tolist(["ALL_PRIVILEGES"]) }] : [],
      contains(["gold", "ref"], s) ? [for p in local.readers : { principal = p, privileges = tolist(["USE_SCHEMA", "SELECT"]) }] : [],
      s == "silver" ? [for p in local.iaml : { principal = p, privileges = tolist(["USE_SCHEMA"]) }] : [],
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

# ia-ml lee tablas puntuales de silver (data.silver tiene a ia-ml como consumer). Primera: call_transcripts,
# para el etiquetado de intención (M5). databricks_grant (singular) no es autoritativo: suma este permiso
# sin tocar los que datos o sp-pipelines tengan sobre la tabla. La tabla la crea el pipeline de datos.
locals {
  iaml_silver_tables = ["call_transcripts"]
  iaml_silver_select = { for pair in setproduct(local.iaml, local.iaml_silver_tables) : "${pair[0]}/${pair[1]}" => { principal = pair[0], table = pair[1] } }
}

resource "databricks_grant" "iaml_silver_select" {
  for_each   = local.iaml_silver_select
  table      = "${databricks_catalog.hackathon.name}.${databricks_schema.this["silver"].name}.${each.value.table}"
  principal  = each.value.principal
  privileges = ["SELECT"]
}

