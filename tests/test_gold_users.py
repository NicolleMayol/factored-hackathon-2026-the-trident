"""agent.cli.USERS: los alias cambian a clientes de gold solo con AGENT_SQL=real y eval/users_gold.json presente."""
import importlib
import json


def _reload(monkeypatch, sql_mode):
    import agent.cli as cli
    monkeypatch.setenv("AGENT_SQL", sql_mode)
    monkeypatch.setattr("pathlib.Path.exists", lambda self: True)
    monkeypatch.setattr("pathlib.Path.read_text", lambda self, encoding=None: json.dumps({"cliente_ar_no": {"customer_id": "CLI-X", "picked_by": "t"}}))
    return importlib.reload(cli)


def test_mock_keeps_fixture(monkeypatch):
    assert _reload(monkeypatch, "mock").USERS["cliente_ar_no"]["customer_id"] == "TEST-AR-003"


def test_real_uses_gold(monkeypatch):
    cli = _reload(monkeypatch, "real")
    assert cli.USERS["cliente_ar_no"]["customer_id"] == "CLI-X"
    assert cli.USERS["cliente_ar_no"]["scopes"] == ["customer:read", "credit:simulate"]
    monkeypatch.undo(); importlib.reload(cli)  # deja USERS como estaba para el resto de la suite
