"""Credenciales Databricks resueltas en un solo lugar (ADR-21 §3). Orden:
  1. DATABRICKS_TOKEN                      token personal (solo si alguien lo tiene; no es el camino por defecto)
  2. DATABRICKS_CLIENT_ID/SECRET           sp-agent-ro, OAuth M2M (Azure Function; valores en Key Vault)
  3. DATABRICKS_CONFIG_PROFILE (o DEFAULT) perfil de la CLI: `databricks auth login --host ... --profile fh26` (local, OAuth U2M con el usuario de Entra)
Nada de esto vive en el repo: .env está en .gitignore y el perfil queda en ~/.databrickscfg."""
from __future__ import annotations
import os
import time
from typing import Callable

_cache: dict[str, object] = {}


def host() -> str:
    h = os.environ.get("DATABRICKS_HOST", "").rstrip("/")
    if h:
        return h
    try:
        from databricks.sdk.core import Config
        return (Config(profile=os.environ.get("DATABRICKS_CONFIG_PROFILE") or None).host or "").rstrip("/")
    except Exception:  # noqa: BLE001
        return ""


def _m2m() -> str:
    import requests
    tok, exp = _cache.get("m2m"), float(_cache.get("m2m_exp", 0))
    if tok and time.time() < exp - 60:
        return str(tok)
    r = requests.post(f"{host()}/oidc/v1/token", auth=(os.environ["DATABRICKS_CLIENT_ID"], os.environ["DATABRICKS_CLIENT_SECRET"]),
                      data={"grant_type": "client_credentials", "scope": "all-apis"}, timeout=10)
    r.raise_for_status(); j = r.json()
    _cache["m2m"], _cache["m2m_exp"] = j["access_token"], time.time() + j.get("expires_in", 3600)
    return j["access_token"]


def _profile_headers() -> Callable[[], dict[str, str]]:
    from databricks.sdk.core import Config
    cfg = Config(profile=os.environ.get("DATABRICKS_CONFIG_PROFILE") or None)
    return cfg.authenticate  # refresca el OAuth U2M solo; devuelve {"Authorization": "Bearer ..."}


def auth_headers() -> dict[str, str]:
    if os.environ.get("DATABRICKS_TOKEN"):
        return {"Authorization": f"Bearer {os.environ['DATABRICKS_TOKEN']}"}
    if os.environ.get("DATABRICKS_CLIENT_ID") and os.environ.get("DATABRICKS_CLIENT_SECRET"):
        return {"Authorization": f"Bearer {_m2m()}"}
    fn = _cache.get("profile_fn")
    if fn is None:
        try:
            fn = _profile_headers()
        except Exception as e:  # noqa: BLE001
            raise RuntimeError("sin credenciales Databricks: usa `databricks auth login --host <host> --profile fh26` y DATABRICKS_CONFIG_PROFILE=fh26 "
                               f"(o DATABRICKS_CLIENT_ID/SECRET en Azure). Detalle: {type(e).__name__}: {str(e)[:120]}") from e
        _cache["profile_fn"] = fn
    return dict(fn())  # type: ignore[operator]


def mode() -> str:
    if os.environ.get("DATABRICKS_TOKEN"):
        return "pat"
    if os.environ.get("DATABRICKS_CLIENT_ID"):
        return "sp-oauth"
    return f"profile:{os.environ.get('DATABRICKS_CONFIG_PROFILE') or 'DEFAULT'}"
