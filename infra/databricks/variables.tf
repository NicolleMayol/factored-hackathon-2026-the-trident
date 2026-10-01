# Correos de Databricks de cada rol. Llegan de variables de GitHub (DATOS_USERS, IAML_USERS) para no
# dejar correos en el repo público. Eladio ya existe en el workspace; ia-ml la crea identities.tf.
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
