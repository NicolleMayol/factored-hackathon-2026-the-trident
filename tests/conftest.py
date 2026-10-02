import os
import pytest

os.environ.setdefault("AGENT_LLM", "mock"); os.environ.setdefault("AGENT_SQL", "mock"); os.environ.setdefault("AGENT_STORE", "mock")
os.environ.setdefault("AGENT_EMBED", "mock"); os.environ.setdefault("AGENT_PRESCORE", "mock"); os.environ.setdefault("AGENT_TRACE", "mock")

from agent.config.settings import get_settings  # noqa: E402
from agent.adapters import build_deps  # noqa: E402
from agent.handle import runtime  # noqa: E402


@pytest.fixture(scope="session")
def settings():
    return get_settings()


@pytest.fixture(scope="session")
def deps(settings):
    return build_deps(settings)


@pytest.fixture(scope="session")
def rt(settings, deps):
    return runtime(settings, deps)


USERS = {
    "cliente_co_ok": {"customer_id": "TEST-CO-001", "scopes": ["customer:read", "credit:simulate"], "locale": "es-CO"},
    "cliente_mx_cond": {"customer_id": "TEST-MX-002", "scopes": ["customer:read", "credit:simulate"], "locale": "es-MX"},
    "cliente_ar_no": {"customer_id": "TEST-AR-003", "scopes": ["customer:read", "credit:simulate"], "locale": "es-AR"},
    "cliente_co_pt": {"customer_id": "TEST-CO-004", "scopes": ["customer:read", "credit:simulate"], "locale": "pt-BR"},
    "cliente_solo_lectura": {"customer_id": "TEST-MX-005", "scopes": ["customer:read"], "locale": "es-MX"},
    "analista": {"customer_id": "AGENT-001", "scopes": ["handoff:read"], "locale": "es-MX"},
}


@pytest.fixture
def users():
    return USERS
