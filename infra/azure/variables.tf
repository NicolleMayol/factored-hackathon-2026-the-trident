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

variable "iaml_object_ids" {
  description = "Object ids de Entra de ia-ml con lectura del secreto cosmos-key (correr el agente en local con AGENT_STORE=real)."
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
  description = "Endpoint de FM APIs para el LLM principal (ADR-02). Claude no aparece en el workspace trial; se revisa al pasar a Premium."
  type        = string
  default     = "databricks-meta-llama-3-3-70b-instruct"
}

variable "fm_endpoint_small" {
  type    = string
  default = "databricks-meta-llama-3-1-8b-instruct"
}

variable "agent_modes" {
  description = "AGENT_* de la Function (ADR-21): mock o real por dependencia. Real solo donde el recurso existe y responde."
  type        = map(string)
  default = {
    llm      = "real" # FM APIs (llama-3.3-70b / llama-3.1-8b) con sp-agent-ro
    sql      = "mock" # gold por wh-agent: pasar a real tras probar check_access A2 con sp-agent-ro
    store    = "mock" # store_cosmos sin implementar: chunks desde data/mock con coseno + BM25 en memoria
    embed    = "mock" # embed-bge-m3 sin registrar (M9)
    prescore = "mock" # prescore-lgbm sin desplegar
    trace    = "mock" # ops.agent_turns en /tmp; MLflow cuando trace_mlflow esté probado
  }
  validation {
    condition     = alltrue([for v in values(var.agent_modes) : contains(["mock", "real"], v)])
    error_message = "Cada modo debe ser mock o real."
  }
}
