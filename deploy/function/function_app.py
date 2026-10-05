"""Raíz del paquete de la Function App. La arma .github/workflows/deploy.yml junto con agent/,
policy/, contracts/ y data/mock/. Las rutas del agente viven en agent/function_app.py (ia-ml);
aquí solo va lo de servicio: POST /session (N4) y preparar el disco.

En Flex Consumption el paquete es de solo lectura. Los adaptadores locales escriben en
AGENT_MOCK_DIR (trazas de ops.agent_turns), así que data/mock se copia a /tmp antes de importar
el agente.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "data" / "mock"
_DST = Path(os.environ.get("AGENT_MOCK_DIR", "/tmp/fh26-mock"))
if _DST != _SRC and not (_DST / "policy_chunks.jsonl").exists():
    shutil.copytree(_SRC, _DST, dirs_exist_ok=True)

import azure.functions as func  # noqa: E402

from agent.auth import issue_test_token  # noqa: E402
from agent.cli import USERS  # noqa: E402
from agent.function_app import S, _json, app  # noqa: E402,F401

# Usuarios de prueba de docs/test-users.md: 5 clientes + el analista (handoff:read).
SESSION_USERS = {**USERS, "analista": {"customer_id": "AGENT-001", "scopes": ["handoff:read"], "locale": "es-MX"}}
JWT_EXP_MIN = 30  # contracts/infra.yaml · identity_mock.jwt_exp_min


@app.route(route="session", methods=["POST"])
def session(req: func.HttpRequest) -> func.HttpResponse:
    """Emite un JWT de prueba (ADR-12). Solo para los usuarios de docs/test-users.md."""
    try:
        user = (req.get_json() or {}).get("user", "")
    except ValueError:
        user = ""
    u = SESSION_USERS.get(user)
    if not u:
        return _json(400, {"error": "unknown_user", "users": sorted(SESSION_USERS)})
    token = issue_test_token(u["customer_id"], u["scopes"], S.jwt_signing_key, exp_min=JWT_EXP_MIN, locale=u["locale"])
    return _json(200, {"token": token, "user": user, "scopes": u["scopes"], "locale": u["locale"], "exp_min": JWT_EXP_MIN})
