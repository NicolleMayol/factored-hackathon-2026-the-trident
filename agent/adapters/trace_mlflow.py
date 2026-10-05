"""Trazas reales: cada turno se escribe en hackathon.ops.agent_turns (contracts/ops.yaml v3) por la Statement API de wh-agent,
en un hilo aparte: la traza nunca añade latencia ni bloquea la respuesta. Los spans por nodo quedan en memoria (los lee el harness).
MLflow se usa para experimentos (eval/, ml/), no para el turno a turno: un run por turno costaría más que el turno.
Misma interfaz que TraceLocal. Requiere SQL_HTTP_PATH y USE SCHEMA + CREATE TABLE en ops (grants de ia-ml, infra.yaml)."""
from __future__ import annotations
import json
import logging
import threading
import time
from contextlib import contextmanager
from typing import Any
import requests
from agent.adapters import dbx_auth

log = logging.getLogger("agent.trace")
TABLE = "hackathon.ops.agent_turns"
COLUMNS = ["ts", "trace_id", "conversation_id", "locale", "node_path", "tools_called", "rules_fired", "expected_action", "action", "escalate_reason",
           "guardrail_hits", "groundedness", "tokens_in", "tokens_out", "cost_usd", "latency_ms", "prompt_version", "model_version", "reply_source"]
ARRAYS = {"node_path", "tools_called", "rules_fired", "guardrail_hits"}
DDL = (f"CREATE TABLE IF NOT EXISTS {TABLE} (ts TIMESTAMP, trace_id STRING, conversation_id STRING, locale STRING, node_path ARRAY<STRING>, "
       "tools_called ARRAY<STRING>, rules_fired ARRAY<STRING>, expected_action STRING, action STRING, escalate_reason STRING, guardrail_hits ARRAY<STRING>, "
       "groundedness DOUBLE, tokens_in INT, tokens_out INT, cost_usd DOUBLE, latency_ms DOUBLE, prompt_version STRING, model_version STRING, reply_source STRING)")


class TraceMlflow:
    def __init__(self, settings):
        self.s = settings
        self.host = (settings.databricks_host or dbx_auth.host()).rstrip("/")
        self.warehouse_id = (settings.sql_http_path or "").rstrip("/").split("/")[-1]
        if not self.warehouse_id:
            raise RuntimeError("trace: falta SQL_HTTP_PATH")
        self.spans: list[dict[str, Any]] = []
        self.pending: list[threading.Thread] = []
        self.errors = 0
        self._ddl_done = False

    @contextmanager
    def span(self, name: str, **attrs: Any):
        t0 = time.perf_counter()
        try:
            yield
        finally:
            self.spans.append({"name": name, "ms": round((time.perf_counter() - t0) * 1000, 1), **attrs})

    def log_turn(self, row: dict[str, Any]) -> None:
        t = threading.Thread(target=self._insert, args=(dict(row),), daemon=True)
        t.start()
        self.pending = [p for p in self.pending if p.is_alive()] + [t]

    def flush(self, timeout: float = 15.0) -> None:
        """Para tests y para el harness: espera las escrituras en vuelo."""
        for t in self.pending:
            t.join(timeout)

    # --- escritura ---
    def _sql(self, statement: str, parameters: list[dict[str, str]]) -> dict[str, Any]:
        r = requests.post(f"{self.host}/api/2.0/sql/statements", headers={**dbx_auth.auth_headers(), "Content-Type": "application/json"},
                          json={"warehouse_id": self.warehouse_id, "statement": statement, "parameters": parameters, "wait_timeout": "30s", "on_wait_timeout": "CANCEL"},
                          timeout=40)
        r.raise_for_status()
        j = r.json()
        if j.get("status", {}).get("state") != "SUCCEEDED":
            raise RuntimeError(j.get("status", {}).get("error", {}).get("message", j.get("status")))
        return j

    def _insert(self, row: dict[str, Any]) -> None:
        try:
            if not self._ddl_done:
                self._sql(DDL, []); self._ddl_done = True
            cols, vals, params = [], [], []
            for c in COLUMNS:
                v = row.get(c)
                cols.append(c)
                if c == "ts":
                    vals.append("current_timestamp()")
                elif c in ARRAYS:
                    vals.append(f"from_json(:{c}, 'array<string>')"); params.append({"name": c, "value": json.dumps(list(v or []), ensure_ascii=False), "type": "STRING"})
                elif v is None:
                    vals.append("NULL")
                elif isinstance(v, bool):
                    vals.append(f":{c}"); params.append({"name": c, "value": str(v).lower(), "type": "BOOLEAN"})
                elif isinstance(v, int):
                    vals.append(f":{c}"); params.append({"name": c, "value": str(v), "type": "INT"})
                elif isinstance(v, float):
                    vals.append(f":{c}"); params.append({"name": c, "value": repr(float(v)), "type": "DOUBLE"})
                else:
                    vals.append(f":{c}"); params.append({"name": c, "value": str(v), "type": "STRING"})
            self._sql(f"INSERT INTO {TABLE} ({', '.join(cols)}) VALUES ({', '.join(vals)})", params)
        except Exception as e:  # noqa: BLE001 — la traza nunca rompe el turno
            self.errors += 1
            log.warning("ops.agent_turns: %s: %s", type(e).__name__, str(e)[:200])
