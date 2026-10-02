"""LLM real: Databricks Foundation Model APIs (endpoints OpenAI-compatible). Understand → FM_ENDPOINT_SMALL; Verify/Respond → FM_ENDPOINT_MAIN.
Misma interfaz que LLMMock: complete(prompt, schema, model) -> dict. Salida JSON validada; un reintento si no parsea; timeout 8 s; cuenta tokens y costo."""
from __future__ import annotations
import json
import re
import time
from typing import Any
import requests
from agent.adapters import dbx_auth

# aprox. pay-per-token por endpoint (USD por 1K tokens in/out); se recalibra con system.billing.usage
PRICE_USD_PER_1K = {"databricks-meta-llama-3-1-8b-instruct": (0.0002, 0.0006), "databricks-meta-llama-3-3-70b-instruct": (0.001, 0.003),
                    "databricks-gpt-oss-20b": (0.0003, 0.0012), "databricks-gpt-oss-120b": (0.0006, 0.0024), "databricks-claude-sonnet-5": (0.003, 0.015)}
DEFAULT_PRICE = {"main": (0.001, 0.003), "small": (0.0002, 0.0006)}


class LLMFmApi:
    def __init__(self, settings):
        self.s = settings
        self.host = settings.databricks_host.rstrip("/") or dbx_auth.host()
        self.last_usage: dict[str, Any] = {}
        self.model_version = f"{settings.fm_endpoint_main}|{settings.fm_endpoint_small}"

    def _post(self, endpoint: str, body: dict) -> requests.Response:
        """429 (cuota por minuto del workspace) → espera Retry-After o 2·4·8 s, hasta 4 intentos; otros errores suben tal cual."""
        for i in range(4):
            r = requests.post(f"{self.host}/serving-endpoints/{endpoint}/invocations", timeout=self.s.tool_timeout_s,
                              headers={**dbx_auth.auth_headers(), "Content-Type": "application/json"}, json=body)
            if getattr(r, "status_code", 200) != 429 or i == 3:
                r.raise_for_status(); return r
            wait = float(r.headers.get("Retry-After") or 2 ** (i + 1))
            self.retries_429 = getattr(self, "retries_429", 0) + 1
            time.sleep(min(wait, 30))
        return r  # pragma: no cover

    def complete(self, prompt: str, schema: dict | None = None, *, model: str = "main") -> dict[str, Any]:
        endpoint = self.s.fm_endpoint_small if model == "small" else self.s.fm_endpoint_main
        task = (schema or {}).get("task")
        system = {"understand": "Devuelve únicamente un objeto JSON válido, sin texto adicional.",
                  "verify": "Eres un verificador. Devuelve únicamente JSON: {\"ok\": bool, \"notes\": [str]}.",
                  "respond": "Eres el agente de crédito del banco. Devuelve únicamente JSON: {\"reply\": str}."}.get(task, "Devuelve únicamente JSON.")
        last_err = None
        for attempt in range(2):
            t0 = time.time()
            r = self._post(endpoint, {"messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}], "max_tokens": 1500 if "gpt-oss" in endpoint else 600, "temperature": 0})
            j = r.json()
            text = _content_text(j.get("choices", [{}])[0].get("message", {}).get("content", ""))
            usage = j.get("usage", {}) or {}
            pin, pout = PRICE_USD_PER_1K.get(endpoint, DEFAULT_PRICE["small" if model == "small" else "main"])
            self.last_usage = {"tokens_in": usage.get("prompt_tokens", 0), "tokens_out": usage.get("completion_tokens", 0),
                               "cost_usd": round(usage.get("prompt_tokens", 0) / 1000 * pin + usage.get("completion_tokens", 0) / 1000 * pout, 6),
                               "latency_ms": round((time.time() - t0) * 1000, 1), "endpoint": endpoint}
            try:
                return _parse_json(text)
            except ValueError as e:
                last_err = e; prompt = prompt + "\n\nLa respuesta anterior no fue JSON válido. Devuelve solo el JSON."
        raise ValueError(f"FM APIs {endpoint}: salida no JSON tras 2 intentos: {last_err}")


def _content_text(c) -> str:
    """OpenAI-compatible: str, o lista de partes (gpt-oss: [{type: reasoning...}, {type: text, text: ...}])."""
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "\n".join(p.get("text", "") for p in c if isinstance(p, dict) and p.get("type") in (None, "text", "output_text"))
    return str(c or "")


def _parse_json(text: str) -> dict[str, Any]:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError(text[:120])
    return json.loads(m.group(0))
