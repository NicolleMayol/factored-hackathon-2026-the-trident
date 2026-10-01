# Correos de Databricks de cada rol. Llegan de variables de GitHub (DATOS_USERS, IAML_USERS) para no
# dejar correos en el repo público. Eladio ya existe en el workspace; ia-ml la crea identities.tf.
variable "databricks_account_id" {
  description = "ID de la cuenta de Databricks (accounts.azuredatabricks.net, menú de usuario)."
  type        = string
}

variable "existing_metastore_id" {
  description = "Vacío: Terraform crea metastore-eastus2. Con un ID: usa ese metastore (la cuenta admite uno por región)."
  type        = string
  default     = ""
}

variable "datos_users" {
  description = "Usuarios del rol datos (Eladio)."
  type        = list(string)
  default     = []
}

variable "iaml_users" {
  description = "Usuarios del rol ia-ml (Manuela)."
  type        = list(string)
  default     = []
}
