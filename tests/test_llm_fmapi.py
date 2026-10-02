"""Adaptador real de FM APIs sin red: se simula el endpoint para probar parseo, reintento, tokens y costo."""
import json
import types
import pytest
from agent.adapters.llm_fmapi import LLMFmApi, _parse_json
from agent.config.settings import get_settings


class _Resp:
    def __init__(self, content, tokens=(10, 5)):
        self._j = {"choices": [{"message": {"content": content}}], "usage": {"prompt_tokens": tokens[0], "completion_tokens": tokens[1]}}
    def raise_for_status(self): pass
    def json(self): return self._j


def test_parse_json_tolera_texto_alrededor():
    assert _parse_json('Claro: {"intent": "product_info"} listo')["intent"] == "product_info"
    with pytest.raises(ValueError):
        _parse_json("sin json")


def test_complete_reintenta_una_vez_y_cuenta_tokens(monkeypatch):
    monkeypatch.setenv("DATABRICKS_TOKEN", "x"); monkeypatch.setenv("DATABRICKS_HOST", "https://example.invalid")
    llm = LLMFmApi(get_settings())
    calls = iter([_Resp("no json"), _Resp(json.dumps({"intent": "product_info", "intent_confidence": 0.9}))])
    monkeypatch.setattr("agent.adapters.llm_fmapi.requests.post", lambda *a, **k: next(calls))
    out = llm.complete("hola", {"task": "understand"}, model="small")
    assert out["intent"] == "product_info" and llm.last_usage["tokens_in"] == 10 and llm.last_usage["cost_usd"] > 0


def test_complete_falla_tras_dos_intentos(monkeypatch):
    monkeypatch.setenv("DATABRICKS_TOKEN", "x"); monkeypatch.setenv("DATABRICKS_HOST", "https://example.invalid")
    llm = LLMFmApi(get_settings())
    monkeypatch.setattr("agent.adapters.llm_fmapi.requests.post", lambda *a, **k: _Resp("nada"))
    with pytest.raises(ValueError):
        llm.complete("hola", {"task": "understand"})


def test_429_reintenta_y_luego_ok(monkeypatch):
    """Cuota por minuto: un 429 con Retry-After se espera y se reintenta; el segundo intento responde."""
    import agent.adapters.llm_fmapi as mod
    from agent.config.settings import Settings
    calls = {"n": 0}

    class R:
        def __init__(self, code, body=None, headers=None):
            self.status_code, self._b, self.headers = code, body, headers or {}
        def json(self): return self._b
        def raise_for_status(self):
            if self.status_code >= 400: raise mod.requests.HTTPError(str(self.status_code))

    def fake_post(url, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return R(429, headers={"Retry-After": "0"})
        return R(200, {"choices": [{"message": {"content": '{"intent": "x"}'}}], "usage": {"prompt_tokens": 5, "completion_tokens": 2}})
    monkeypatch.setattr(mod.requests, "post", fake_post)
    monkeypatch.setattr(mod.dbx_auth, "auth_headers", lambda: {"Authorization": "Bearer t"})
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    monkeypatch.setenv("DATABRICKS_HOST", "https://x")
    llm = mod.LLMFmApi(Settings())
    assert llm.complete("hola", {"task": "understand"}, model="small") == {"intent": "x"}
    assert calls["n"] == 2 and llm.retries_429 == 1
