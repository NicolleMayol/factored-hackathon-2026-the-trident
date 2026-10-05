"""Adaptador real (sql_warehouse): consultas a gold por wh-agent con la API de SQL Statements.

Misma interfaz que sql_csv. Credenciales de dbx_auth (sp-agent-ro por OAuth M2M en Azure; perfil de
la CLI en local). Solo los datos del cliente vienen de gold; el catálogo y las tasas de regulador se
leen de los CSV que genera datos (E5, E6), que son la misma fuente que alimenta gold y ref.
"""
from __future__ import annotations

import time
from typing import Any

import requests

from agent.adapters import dbx_auth
from agent.adapters.sql_csv import SQLCsv, _typed

CATALOG = "hackathon"
# nombre lógico → (tabla, columna llave). Columnas = contracts/gold.yaml (las mismas del mock).
GOLD = {
    "customer_profile": ("gold.customer_360", "customer_id"),
    "customer_products": ("gold.customer_products", "customer_id"),
    "customer_behavior": ("gold.customer_behavior_12m", "customer_id"),
}
WAIT_S = 6  # dentro del timeout de 8 s de las tools (contracts/tools.yaml)


class SQLWarehouse:
    def __init__(self, settings):
        path = (settings.sql_http_path or "").rstrip("/")
        self.warehouse_id = path.rsplit("/", 1)[-1]
        if not self.warehouse_id:
            raise ValueError("SQL_HTTP_PATH vacío: /sql/1.0/warehouses/<id>")
        self.host = dbx_auth.host()
        self.csv = SQLCsv(settings)

    def query(self, name: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        if name not in GOLD:
            return self.csv.query(name, params)
        table, key = GOLD[name]
        return self._run(f"SELECT * FROM {CATALOG}.{table} WHERE {key} = :v", {"v": params.get(key)})

    def _run(self, statement: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        body = {
            "warehouse_id": self.warehouse_id,
            "statement": statement,
            "parameters": [{"name": k, "value": None if v is None else str(v)} for k, v in params.items()],
            "wait_timeout": f"{max(WAIT_S, 5)}s",  # la API acepta 0 o 5–50 s
            "on_wait_timeout": "CONTINUE",
            "format": "JSON_ARRAY",
            "disposition": "INLINE",
        }
        url = f"{self.host}/api/2.0/sql/statements"
        r = requests.post(url, json=body, headers=dbx_auth.auth_headers(), timeout=WAIT_S + 4)
        r.raise_for_status()
        j = r.json()
        deadline = time.monotonic() + 20
        while j.get("status", {}).get("state") in ("PENDING", "RUNNING") and time.monotonic() < deadline:
            time.sleep(0.5)  # warehouse en frío: la tool reintenta si se pasa del timeout
            r = requests.get(f"{url}/{j['statement_id']}", headers=dbx_auth.auth_headers(), timeout=10)
            r.raise_for_status()
            j = r.json()
        state = j.get("status", {}).get("state")
        if state != "SUCCEEDED":
            err = j.get("status", {}).get("error", {}).get("message", "")
            raise RuntimeError(f"sql_warehouse: {state} {err[:200]}")
        cols = [c["name"] for c in j["manifest"]["schema"]["columns"]]
        rows = j.get("result", {}).get("data_array") or []
        return [_typed({c: ("" if v is None else v) for c, v in zip(cols, row)}) for row in rows]
