variable "location" {
  type    = string
  default = "eastus2"
}

variable "budget_amount" {
  description = "USD por mes para las alertas de presupuesto. Ajustar cuando se conozcan los créditos."
  type        = number
  default     = 100
}

variable "budget_emails" {
  description = "Correos que reciben las alertas de presupuesto."
  type        = list(string)
  default     = []
}

variable "admin_object_ids" {
  description = "Object IDs de personas que pueden leer secretos en el Key Vault (portal)."
  type        = list(string)
  default     = []
}

variable "function_always_ready" {
  description = "true solo en la ventana de jurado (1 instancia caliente)."
  type        = bool
  default     = false
}

# Valores que llegan del stack de Databricks (mañana, tras account admin). Vacíos hasta entonces.
variable "databricks_client_id" {
  description = "Application ID de sp-agent-ro."
  type        = string
  default     = ""
}

variable "sql_http_path" {
  description = "HTTP path de wh-agent."
  type        = string
  default     = ""
}

variable "fm_endpoint_main" {
  description = "Endpoint de FM APIs para el LLM principal (ADR-02)."
  type        = string
  default     = "databricks-claude-sonnet-5"
}

variable "fm_endpoint_small" {
  type    = string
  default = "databricks-meta-llama-3-1-8b-instruct"
}
