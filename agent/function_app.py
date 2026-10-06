"""Azure Functions (modelo v2). Rutas de contracts/api.yaml. auth_level ANONYMOUS: el JWT se valida en código."""
from __future__ import annotations
import json
import logging
import azure.functions as func

from agent.auth import AuthError, decode_token, require_scope
from agent.config.settings import get_settings
from agent import handle as H

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)
S = get_settings()


def _json(status: int, body: dict) -> func.HttpResponse:
    return func.HttpResponse(json.dumps(body, ensure_ascii=False), status_code=status, mimetype="application/json")


def _auth(req: func.HttpRequest, scope: str | None = None) -> dict:
    tok = (req.headers.get("Authorization") or "").removeprefix("Bearer ").strip()
    claims = decode_token(tok, S.jwt_signing_key)
    if scope:
        require_scope(claims, scope)
    return claims


@app.route(route="chat", methods=["POST"])
def chat(req: func.HttpRequest) -> func.HttpResponse:
    try:
        claims = _auth(req)
        body = req.get_json()
        out = H.handle(body["message"], {"customer_id": claims["customer_id"], "scopes": claims["scopes"], "locale": H.pick_locale(body.get("locale"), claims.get("locale")),
                                         "conversation_id": body.get("conversation_id"), "trace_id": req.headers.get("x-trace-id")})
        out.pop("_state", None)
        return _json(200, out)
    except AuthError as e:
        return _json(e.status, {"error": e.code})
    except Exception:  # noqa: BLE001
        logging.exception("chat")
        return _json(500, {"error": "internal"})


@app.route(route="chat/confirm", methods=["POST"])
def chat_confirm(req: func.HttpRequest) -> func.HttpResponse:
    try:
        claims = _auth(req)
        body = req.get_json()
        out = H.confirm(body["action_id"], bool(body.get("confirmed")), {"customer_id": claims["customer_id"]})
        return _json(200, out) if out else _json(404, {"error": "action_not_found"})
    except AuthError as e:
        return _json(e.status, {"error": e.code})


@app.route(route="trace/{trace_id}", methods=["GET"])
def trace(req: func.HttpRequest) -> func.HttpResponse:
    try:
        _auth(req, "handoff:read")
    except AuthError as e:
        return _json(e.status, {"error": e.code})
    return _json(501, {"error": "pendiente: lectura de ops.agent_turns"})


@app.route(route="handoff/{case_id}", methods=["GET"])
def handoff(req: func.HttpRequest) -> func.HttpResponse:
    try:
        _auth(req, "handoff:read")
    except AuthError as e:
        return _json(e.status, {"error": e.code})
    _, d, _ = H.runtime()
    doc = d.store.get_handoff(req.route_params["case_id"])
    return _json(200, doc) if doc else _json(404, {"error": "not_found"})


@app.route(route="healthz", methods=["GET"])
def healthz(req: func.HttpRequest) -> func.HttpResponse:
    status, h = H.healthz()
    return _json(status, h)
