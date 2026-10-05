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


# --- GET /insights (ADR-29) -----------------------------------------------------------------
# Los tres hallazgos del notebook de datos (E10, data/insights/insights_demanda.py) servidos en
# vivo para la página insights.html. Solo agregados de gold: ninguna fila de cliente sale del
# tenant (ADR-12). El mismo SQL corre en el warehouse (AGENT_SQL=real) y, en tests y en local,
# sobre data/mock cargado en SQLite, así que las pruebas ejercitan las consultas de producción.
import sqlite3  # noqa: E402
import time  # noqa: E402
from collections import Counter  # noqa: E402
from datetime import datetime, timezone  # noqa: E402

INSIGHTS_TTL_S = 3600  # gold se refresca cada 6 h; una consulta por hora basta
_insights_cache: dict[str, tuple[float, dict]] = {}
_NOT_TEST = "customer_id NOT LIKE 'TEST-%'"  # los TEST-* no existen en el origen (ADR-22)


def _threshold(root: Path = _ROOT) -> int:
    """Umbral de elegibilidad más común del catálogo (min_score), no un número fijo en el código."""
    cat = yaml.safe_load((root / "policy" / "catalog.yaml").read_text(encoding="utf-8"))["products"]
    return Counter(int(p["min_score"]) for p in cat if p.get("min_score") is not None).most_common(1)[0][0]


def _insights_sql(gold: str, t: int) -> dict[str, str]:
    return {
        "demand": f"SELECT reason_category AS category, sum(volume) AS contacts, avg(fcr_rate) AS fcr, avg(csat_avg) AS csat "
                  f"FROM {gold}contact_demand GROUP BY reason_category",
        "segments": f"SELECT segment, count(*) AS customers, avg(credit_score) AS avg_score, "
                    f"sum(CASE WHEN credit_score IS NULL THEN 1 ELSE 0 END) AS no_score, "
                    f"sum(CASE WHEN estimated_monthly_income IS NULL THEN 1 ELSE 0 END) AS no_income, "
                    f"sum(CASE WHEN credit_score < {t} THEN 1 ELSE 0 END) AS below, "
                    f"sum(CASE WHEN credit_score BETWEEN {t - 25} AND {t + 25} THEN 1 ELSE 0 END) AS near "
                    f"FROM {gold}customer_360 WHERE {_NOT_TEST} GROUP BY segment",
    }


def _mock_executor(root: Path = _ROOT):
    """SQLite en memoria con los CSV de data/mock (vacíos → NULL, números → REAL)."""
    db = sqlite3.connect(":memory:")
    for table in ("contact_demand", "customer_360"):
        rows = list(csv.DictReader(open(root / "data" / "mock" / f"{table}.csv", encoding="utf-8")))
        cols = list(rows[0])
        db.execute(f"CREATE TABLE {table} ({', '.join(cols)})")

        def val(v):
            if v == "":
                return None
            try:
                return float(v)
            except ValueError:
                return v
        db.executemany(f"INSERT INTO {table} VALUES ({', '.join('?' * len(cols))})", [[val(r[c]) for c in cols] for r in rows])

    def run(sql: str) -> list[dict]:
        cur = db.execute(sql)
        names = [d[0] for d in cur.description]
        return [dict(zip(names, r)) for r in cur.fetchall()]
    return run


def _pct(a, b) -> float:
    return round(100.0 * float(a or 0) / float(b), 1) if b else 0.0


def build_insights(run, t: int, source: str) -> dict:
    q = _insights_sql("" if source == "mock" else "hackathon.gold.", t)
    demand = sorted(run(q["demand"]), key=lambda r: -float(r["contacts"] or 0))
    total_contacts = sum(float(r["contacts"] or 0) for r in demand)
    segs = sorted(run(q["segments"]), key=lambda r: -float(r["customers"] or 0))
    n = sum(float(r["customers"] or 0) for r in segs)
    return {
        "as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": source,
        "threshold": t,
        "demand": [{"category": r["category"], "contacts": int(float(r["contacts"])), "share_pct": _pct(r["contacts"], total_contacts),
                    "fcr": round(float(r["fcr"]), 3), "csat": round(float(r["csat"]), 2)} for r in demand],
        "segments": [{"segment": r["segment"], "customers": int(float(r["customers"])), "share_pct": _pct(r["customers"], n),
                      "avg_score": round(float(r["avg_score"])) if r["avg_score"] is not None else None,
                      "below_threshold_pct": _pct(r["below"], float(r["customers"]) - float(r["no_score"] or 0)),
                      "near_threshold_pct": _pct(r["near"], float(r["customers"]) - float(r["no_score"] or 0))} for r in segs],
        "coverage": {"customers": int(n), "no_score_pct": _pct(sum(float(r["no_score"] or 0) for r in segs), n),
                     "no_income_pct": _pct(sum(float(r["no_income"] or 0) for r in segs), n)},
    }


def _insights() -> dict:
    hit = _insights_cache.get("v")
    if hit and time.time() - hit[0] < INSIGHTS_TTL_S:
        return hit[1]
    if S.agent_sql == "real":
        from agent.adapters.sql_warehouse import SQLWarehouse
        wh = SQLWarehouse(S)
        body = build_insights(lambda sql: wh._execute(sql, []), _threshold(), "gold")
    else:
        body = build_insights(_mock_executor(), _threshold(), "mock")
    _insights_cache["v"] = (time.time(), body)
    return body


@app.route(route="insights", methods=["GET"])
def insights(req: func.HttpRequest) -> func.HttpResponse:
    """Público, sin JWT. Solo agregados de gold (ADR-12); caché de una hora."""
    try:
        body = _insights()
    except Exception:  # noqa: BLE001 — warehouse frío o caído: la página reintenta; nunca un 500 con detalles internos
        import logging
        logging.exception("insights: no se pudo consultar gold")
        return _json(503, {"error": "unavailable"})
    return func.HttpResponse(json.dumps(body, ensure_ascii=False), status_code=200, mimetype="application/json",
                             headers={"Cache-Control": "public, max-age=3600"})
