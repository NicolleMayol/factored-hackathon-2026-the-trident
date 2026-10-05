"""SQL real: Databricks SQL Statement Execution API sobre wh-agent (serverless). Misma firma que SQLCsv.

Lee gold/ref con las credenciales de dbx_auth (perfil local, sp-agent-ro en Azure). Sin conector pesado: HTTP puro,
consultas parametrizadas (nunca interpolación), timeout corto en caliente y tolerancia a frío (ADR-21 §2b).
Las tablas de referencia (tasas, catálogo) se cachean 10 min; las de cliente, nunca.
"""
from __future__ import annotations
import time
from typing import Any
import requests
from agent.adapters import dbx_auth

CATALOG = "hackathon"
QUERIES = {
    "customer_profile": ("SELECT customer_id, country, country_code, segment, credit_score, estimated_monthly_income, customer_status, detected_accent "
                         f"FROM {CATALOG}.gold.customer_360 WHERE customer_id = :customer_id", ["customer_id"]),
    "customer_products": ("SELECT product_id, customer_id, product_type, currency, current_balance, credit_limit, days_past_due, product_status "
                          f"FROM {CATALOG}.gold.customer_products WHERE customer_id = :customer_id", ["customer_id"]),
    "customer_behavior": ("SELECT customer_id, n_tx, amount_usd_12m, declined_ratio, max_days_past_due, active_months "
                          f"FROM {CATALOG}.gold.customer_behavior_12m WHERE customer_id = :customer_id", ["customer_id"]),
    "regulator_rates": ("SELECT country, product_type, rate_kind, rate_min, rate_max, source, url, snapshot_date "
                        f"FROM {CATALOG}.ref.regulator_rates WHERE country = :country", ["country"]),
    "product_catalog": ("SELECT product_code, country, name_es, name_pt, product_type, product_type_dataset, min_score, currency, rate_min, rate_max, amount_min, amount_max, term_months_max "
                        f"FROM {CATALOG}.gold.credit_product_catalog WHERE country = :country", ["country"]),
}
CACHEABLE = {"regulator_rates": 600, "product_catalog": 600}
NUMERIC = {"INT", "BIGINT", "SMALLINT", "TINYINT", "DECIMAL", "DOUBLE", "FLOAT", "LONG"}


class SQLWarehouse:
    def __init__(self, settings):
        self.s = settings
        self.host = (settings.databricks_host or dbx_auth.host()).rstrip("/")
        path = settings.sql_http_path or ""
        self.warehouse_id = path.rstrip("/").split("/")[-1]
        if not self.warehouse_id:
            raise RuntimeError("sql_warehouse: falta SQL_HTTP_PATH (/sql/1.0/warehouses/<id>)")
        self._cache: dict[tuple, tuple[float, list[dict[str, Any]]]] = {}
        self.last_ms = 0.0

    # --- API ---
    def query(self, name: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        sql, keys = QUERIES[name]
        ckey = (name, tuple(params.get(k) for k in keys))
        ttl = CACHEABLE.get(name)
        if ttl and ckey in self._cache and time.time() - self._cache[ckey][0] < ttl:
            rows = self._cache[ckey][1]
        else:
            rows = self._execute(sql, [{"name": k, "value": str(params.get(k)), "type": "STRING"} for k in keys if params.get(k) is not None])
            if ttl:
                self._cache[ckey] = (time.time(), rows)
        # filtros secundarios que el mock aplica en memoria (product_type en tasas y catálogo)
        if params.get("product_type"):
            rows = [r for r in rows if r.get("product_type") == params["product_type"]]
        return rows

    # --- Statement Execution API ---
    def _execute(self, sql: str, parameters: list[dict[str, str]]) -> list[dict[str, Any]]:
        t0 = time.time()
        body = {"warehouse_id": self.warehouse_id, "statement": sql, "parameters": parameters,
                "wait_timeout": "30s", "on_wait_timeout": "CANCEL", "format": "JSON_ARRAY", "disposition": "INLINE", "row_limit": 1000}
        r = requests.post(f"{self.host}/api/2.0/sql/statements", headers={**dbx_auth.auth_headers(), "Content-Type": "application/json"},
                          json=body, timeout=max(self.s.tool_timeout_cold_s, 30) + 5)
        r.raise_for_status()
        j = r.json()
        state = j.get("status", {}).get("state")
        if state != "SUCCEEDED":
            err = j.get("status", {}).get("error", {}).get("message", state)
            raise RuntimeError(f"sql_warehouse: {state}: {err}")
        cols = j.get("manifest", {}).get("schema", {}).get("columns", [])
        data = j.get("result", {}).get("data_array", []) or []
        self.last_ms = round((time.time() - t0) * 1000, 1)
        return [_typed_row(cols, row) for row in data]


def _typed_row(cols: list[dict[str, Any]], row: list[Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for c, v in zip(cols, row):
        name, t = c["name"], str(c.get("type_name", "")).upper()
        if v is None or v == "":
            out[name] = None
        elif t in ("INT", "BIGINT", "SMALLINT", "TINYINT", "LONG"):
            out[name] = int(float(v))
        elif t in NUMERIC:
            out[name] = float(v)
        elif t == "BOOLEAN":
            out[name] = str(v).lower() == "true"
        else:
            out[name] = v
    return out
