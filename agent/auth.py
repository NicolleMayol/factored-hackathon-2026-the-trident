"""JWT HS256 (ADR-12 cerrada, ADR-21): firma y exp se validan en código; customer_id solo sale del token."""
from __future__ import annotations
import time
from typing import Any
import jwt


class AuthError(Exception):
    def __init__(self, status: int, code: str):
        super().__init__(code); self.status, self.code = status, code


def decode_token(token: str | None, key: str) -> dict[str, Any]:
    if not token:
        raise AuthError(401, "missing_token")
    try:
        claims = jwt.decode(token, key, algorithms=["HS256"], options={"require": ["customer_id", "scopes", "exp"]})
    except jwt.ExpiredSignatureError as e:
        raise AuthError(401, "expired") from e
    except jwt.InvalidTokenError as e:
        raise AuthError(401, "jwt_invalid") from e
    if not isinstance(claims.get("scopes"), list):
        raise AuthError(401, "jwt_invalid")
    return claims


def require_scope(claims: dict[str, Any], scope: str) -> None:
    if scope not in claims.get("scopes", []):
        raise AuthError(403, "scope_missing")


def issue_test_token(customer_id: str, scopes: list[str], key: str, exp_min: int = 30, locale: str = "es-MX") -> str:
    """Solo para local y tests. En Azure lo emite POST /session (servicio)."""
    return jwt.encode({"customer_id": customer_id, "scopes": scopes, "locale": locale, "exp": int(time.time()) + exp_min * 60}, key, algorithm="HS256")
