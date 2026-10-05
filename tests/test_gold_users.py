"""agent.cli.USERS: los alias cambian a clientes de gold solo con AGENT_SQL=real y eval/users_gold.json presente."""
import copy
import json

from agent import cli


def _run(tmp_path, env):
    f = tmp_path / "users_gold.json"
    f.write_text(json.dumps({"cliente_ar_no": {"customer_id": "CLI-X", "picked_by": "t"}}), encoding="utf-8")
    before = copy.deepcopy(cli.USERS)
    try:
        cli._gold_users(path=f, env=env)
        return cli.USERS["cliente_ar_no"]
    finally:
        cli.USERS.clear(); cli.USERS.update(before)  # deja USERS como estaba para el resto de la suite


def test_mock_keeps_fixture(tmp_path):
    assert _run(tmp_path, {"AGENT_SQL": "mock"})["customer_id"] == "TEST-AR-003"


def test_real_uses_gold(tmp_path):
    u = _run(tmp_path, {"AGENT_SQL": "real"})
    assert u["customer_id"] == "CLI-X" and u["scopes"] == ["customer:read", "credit:simulate"]


def test_real_can_opt_out(tmp_path):
    assert _run(tmp_path, {"AGENT_SQL": "real", "EVAL_USERS": "fixture"})["customer_id"] == "TEST-AR-003"
