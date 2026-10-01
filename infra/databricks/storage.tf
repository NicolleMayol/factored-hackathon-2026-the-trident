# Identidad de Unity Catalog sobre ADLS: el Access Connector, que ya tiene Storage Blob Data
# Contributor sobre adlsagentbankdev (infra/azure). Sin file events: la ingesta usa directory listing (ADR-20).
resource "databricks_storage_credential" "adls" {
  name           = "stg-credential-adlsagentbankdev"
  isolation_mode = "ISOLATION_MODE_ISOLATED"
  comment        = "Access Connector acc-agent-bank-dev · Terraform (ADR-20)"
  depends_on     = [databricks_metastore_assignment.this, databricks_grant.metastore_sp]

  azure_managed_identity {
    access_connector_id = data.azurerm_databricks_access_connector.main.id
  }
}

resource "databricks_external_location" "adls" {
  for_each        = local.containers
  name            = "ext-loc-${local.adls}-${each.key}"
  url             = local.url[each.key]
  credential_name = databricks_storage_credential.adls.name
  isolation_mode  = "ISOLATION_MODE_ISOLATED"
  read_only       = each.key == "landing" # landing solo lo escribe azcopy (workflow data-landing)
  comment         = "Terraform (ADR-20)"
}

# Solo landing se lee como archivos. Las demás son managed storage y no llevan READ FILES.
resource "databricks_grants" "landing" {
  external_location = databricks_external_location.adls["landing"].id

  dynamic "grant" {
    for_each = local.writers
    content {
      principal  = grant.value
      privileges = ["READ_FILES"]
    }
  }
}
