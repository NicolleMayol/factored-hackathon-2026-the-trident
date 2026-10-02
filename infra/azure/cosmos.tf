# ADR-04 / ADR-09 · free tier + vector search. La búsqueda vectorial no admite throughput
# compartido, así que cada contenedor lleva 400 RU/s propios (1.200; el free tier cubre 1.000).
resource "azurerm_cosmosdb_account" "main" {
  name                = "cosmos-agent-bank-dev"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  offer_type          = "Standard"
  kind                = "GlobalDocumentDB"
  free_tier_enabled   = true
  tags                = local.tags

  capabilities {
    name = "EnableNoSQLVectorSearch"
  }

  consistency_policy {
    consistency_level = "Session"
  }

  geo_location {
    location          = azurerm_resource_group.main.location
    failover_priority = 0
  }

  # azurerm reemplaza la cuenta si cambian las capabilities de búsqueda (EnableNoSQLFullTextSearch no
  # está en su lista de "se puede agregar"). Las funciones de full-text se activan en el portal
  # (Features) y Terraform no las toca. prevent_destroy: un plan que borre la cuenta falla.
  lifecycle {
    prevent_destroy = true
    ignore_changes  = [capabilities]
  }
}

resource "azurerm_cosmosdb_sql_database" "agent" {
  name                = "agent"
  resource_group_name = azurerm_resource_group.main.name
  account_name        = azurerm_cosmosdb_account.main.name
  # sin throughput a nivel de base: cada contenedor tiene el suyo
}

resource "azurerm_cosmosdb_sql_container" "conversations" {
  name                = "conversations"
  resource_group_name = azurerm_resource_group.main.name
  account_name        = azurerm_cosmosdb_account.main.name
  database_name       = azurerm_cosmosdb_sql_database.agent.name
  partition_key_paths = ["/conversation_id"]
  throughput          = 400
  default_ttl         = 86400
}

resource "azurerm_cosmosdb_sql_container" "handoffs" {
  name                = "handoffs"
  resource_group_name = azurerm_resource_group.main.name
  account_name        = azurerm_cosmosdb_account.main.name
  database_name       = azurerm_cosmosdb_sql_database.agent.name
  partition_key_paths = ["/case_id"]
  throughput          = 400
}

# azurerm no expone vector_embedding_policy ni full_text_policy; se crea con azapi (contracts/chunks.yaml).
# Búsqueda híbrida (ADR-21): RRF de VectorDistance(/embedding) y FullTextScore sobre text_es o text_pt.
# El idioma va por path: cada campo tiene su analizador y el que no aplica llega en null.
# es-ES y pt-BR están en preview: requieren "New features for full-text search" en Features del portal.
resource "azapi_resource" "policy_chunks" {
  type      = "Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2025-10-15"
  name      = "policy_chunks"
  parent_id = azurerm_cosmosdb_sql_database.agent.id

  body = {
    properties = {
      options = { throughput = 400 }
      resource = {
        id = "policy_chunks"
        partitionKey = {
          paths   = ["/country"]
          kind    = "Hash"
          version = 2
        }
        vectorEmbeddingPolicy = {
          vectorEmbeddings = [{
            path             = "/embedding"
            dataType         = "float32"
            dimensions       = 1024
            distanceFunction = "cosine"
          }]
        }
        fullTextPolicy = {
          defaultLanguage = "es-ES"
          fullTextPaths = [
            { path = "/text_es", language = "es-ES" },
            { path = "/text_pt", language = "pt-BR" }, # glosario, documentos y usuarios de prueba de Brasil
          ]
        }
        indexingPolicy = {
          indexingMode    = "consistent"
          automatic       = true
          includedPaths   = [{ path = "/*" }]
          excludedPaths   = [{ path = "/embedding/*" }, { path = "/\"_etag\"/?" }]
          vectorIndexes   = [{ path = "/embedding", type = "diskANN" }]
          fullTextIndexes = [{ path = "/text_es" }, { path = "/text_pt" }]
        }
      }
    }
  }
}
