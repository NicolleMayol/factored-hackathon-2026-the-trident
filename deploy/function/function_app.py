"""Raíz del paquete de la Function App. La arma .github/workflows/deploy.yml junto con agent/,
policy/, contracts/ y data/mock/. Las rutas del agente viven en agent/function_app.py (ia-ml);
aquí solo va lo de servicio: POST /session (N4), GET /meta (ADR-25) y preparar el disco.

En Flex Consumption el paquete es de solo lectura. Los adaptadores locales escriben en
AGENT_MOCK_DIR (trazas de ops.agent_turns), así que data/mock se copia a /tmp antes de importar
el agente.
"""
from __future__ import annotations

import csv
import json
import os
import shutil
from functools import lru_cache
from pathlib import Path

import yaml

# Raíz del paquete; en el repo (tests) este archivo vive en deploy/function/ y la raíz está dos niveles arriba.
_ROOT = Path(__file__).resolve().parent
if not (_ROOT / "policy").exists():
    _ROOT = _ROOT.parents[1]
_SRC = _ROOT / "data" / "mock"
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


# --- GET /meta (ADR-25) ---------------------------------------------------------------------
# La UI no trae datos de negocio quemados: personas, países, productos, resultados posibles y
# motivos de escalamiento salen de los mismos archivos que lee el agente. Agregar un país, un
# producto o un usuario de prueba no toca web/. Los textos de la interfaz viven en web/ui.json.
def _test_countries(root: Path) -> dict[str, str]:
    """country_code de cada cliente TEST-* (filas sintéticas de gold.customer_360, ADR-22)."""
    f = root / "data" / "mock" / "customer_360.csv"
    if not f.exists():
        return {}
    with f.open(encoding="utf-8") as fh:
        return {r["customer_id"]: r["country_code"] for r in csv.DictReader(fh) if r.get("country_code")}


def build_meta(root: Path = _ROOT) -> dict:
    catalog = yaml.safe_load((root / "policy" / "catalog.yaml").read_text(encoding="utf-8"))
    tools = yaml.safe_load((root / "contracts" / "tools.yaml").read_text(encoding="utf-8"))["tools"]
    handoff = json.loads((root / "contracts" / "handoff.schema.json").read_text(encoding="utf-8"))
    countries: dict[str, str] = {}
    products: dict[str, dict] = {}
    for p in catalog["products"]:
        countries.setdefault(p["country"], p.get("country_name") or p["country"])
        products[p["product_code"]] = {
            "country": p["country"], "type": p.get("product_type"), "currency": p.get("currency"),
            "name": {"es": p.get("name_es"), "pt": p.get("name_pt")},
            **{k: p.get(k) for k in ("rate_min", "rate_max", "amount_min", "amount_max", "term_months_max")},
        }
    outcome = next((r["outcome"] for r in tools["evaluate_eligibility"]["returns"] if isinstance(r, dict) and "outcome" in r), "")
    cc = _test_countries(root)
    users = [{"key": k, "locale": u["locale"], "scopes": u["scopes"], "country": cc.get(u["customer_id"])}
             for k, u in SESSION_USERS.items()]
    return {
        "catalog_version": catalog.get("version"),
        "users": users,
        "countries": countries,
        "products": products,
        "tools": sorted(tools),
        "outcomes": [o.strip() for o in outcome.split("|") if o.strip()],
        "reason_codes": handoff["properties"]["reason_code"]["enum"],
    }


@lru_cache(maxsize=1)
def _meta_body() -> str:
    return json.dumps(build_meta(), ensure_ascii=False)


@app.route(route="meta", methods=["GET"])
def meta(req: func.HttpRequest) -> func.HttpResponse:
    """Público, sin JWT ni datos de clientes (solo claves de prueba, locale, scopes y país)."""
    return func.HttpResponse(_meta_body(), status_code=200, mimetype="application/json",
                             headers={"Cache-Control": "public, max-age=300"})
