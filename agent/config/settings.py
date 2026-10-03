"""Configuración leída de entorno. Nombres de App Settings = contracts/infra.yaml. AGENT_* elige mock o real por dependencia (ADR-21)."""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class Settings:
    # modo por dependencia: mock | real
    agent_llm: str = field(default_factory=lambda: _env("AGENT_LLM", "mock"))
    agent_store: str = field(default_factory=lambda: _env("AGENT_STORE", "mock"))
    agent_sql: str = field(default_factory=lambda: _env("AGENT_SQL", "mock"))
    agent_prescore: str = field(default_factory=lambda: _env("AGENT_PRESCORE", "mock"))
    agent_embed: str = field(default_factory=lambda: _env("AGENT_EMBED", "mock"))
    agent_trace: str = field(default_factory=lambda: _env("AGENT_TRACE", "mock"))
    # App Settings (infra.yaml)
    databricks_host: str = field(default_factory=lambda: _env("DATABRICKS_HOST"))
    databricks_client_id: str = field(default_factory=lambda: _env("DATABRICKS_CLIENT_ID"))
    databricks_client_secret: str = field(default_factory=lambda: _env("DATABRICKS_CLIENT_SECRET"))
    sql_http_path: str = field(default_factory=lambda: _env("SQL_HTTP_PATH"))
    respond_llm: str = field(default_factory=lambda: _env("RESPOND_LLM", "auto"))  # auto: LLM solo si AGENT_LLM=real | on | off
    respond_prompt_version: str = field(default_factory=lambda: _env("RESPOND_PROMPT_VERSION", "v2"))
    understand_prompt: str = field(default_factory=lambda: _env("UNDERSTAND_PROMPT", "understand_v2.md"))  # v2: reglas + ejemplos (it. 3, 11 fallas del 70B)
    fm_endpoint_main: str = field(default_factory=lambda: _env("FM_ENDPOINT_MAIN", "databricks-meta-llama-3-3-70b-instruct"))
    fm_endpoint_small: str = field(default_factory=lambda: _env("FM_ENDPOINT_SMALL", "databricks-meta-llama-3-1-8b-instruct"))
    prescore_endpoint: str = field(default_factory=lambda: _env("PRESCORE_ENDPOINT", "prescore-lgbm"))
    embed_endpoint: str = field(default_factory=lambda: _env("EMBED_ENDPOINT", "embed-bge-m3"))
    cosmos_endpoint: str = field(default_factory=lambda: _env("COSMOS_ENDPOINT"))
    cosmos_key: str = field(default_factory=lambda: _env("COSMOS_KEY"))
    mlflow_tracking_uri: str = field(default_factory=lambda: _env("MLFLOW_TRACKING_URI", "databricks"))
    mlflow_experiment: str = field(default_factory=lambda: _env("MLFLOW_EXPERIMENT", "/Shared/fh26/agente"))
    jwt_signing_key: str = field(default_factory=lambda: _env("JWT_SIGNING_KEY", "local-dev-key-change-me"))
    # rutas locales
    mock_dir: Path = field(default_factory=lambda: Path(_env("AGENT_MOCK_DIR", str(REPO_ROOT / "data" / "mock"))))
    policy_path: Path = field(default_factory=lambda: REPO_ROOT / "policy" / "policy.yaml")
    catalog_path: Path = field(default_factory=lambda: Path(_env("AGENT_CATALOG_PATH", str(REPO_ROOT / "data" / "mock" / "catalog.yaml"))))
    glossary_path: Path = field(default_factory=lambda: REPO_ROOT / "policy" / "glossary.yaml")
    prompts_dir: Path = field(default_factory=lambda: REPO_ROOT / "agent" / "prompts")
    # límites (contracts/tools.yaml)
    tool_timeout_s: float = 8.0
    tool_timeout_cold_s: float = 25.0
    tool_retries: int = 2
    max_tool_iterations: int = 2
    jwt_exp_min: int = 30


def get_settings() -> Settings:
    return Settings()
