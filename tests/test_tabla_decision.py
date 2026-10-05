"""ADR-28: tabla de decisión de la pre-evaluación (P02, P05, P07, P10, P11). Una prueba por fila.
Las filas 1–5 y 8 prueban el motor; la 6 y la 7 necesitan el flujo de confirmación, así que pasan por handle()."""
import pytest
from agent.handle import confirm, handle
from agent.policy import engine

POL = "policy/policy.yaml"
SIM = {"intent": "eligibility_simulation", "intent_confidence": 0.9, "scopes": ["customer:read", "credit:simulate"], "jwt_valid": True}

FILAS = [
    # fila, cambios sobre una simulación válida, acción de API esperada, regla que debe ganar, reason_code
    (1, {"jwt_invalid": True, "injection_detected": True, "days_past_due": 5}, "reject", "P11", ""),
    (2, {"injection_detected": True, "days_past_due": 5}, "blocked", "P10", "injection_suspected"),
    (2, {"third_party_data_request": True}, "blocked", "P10", "injection_suspected"),
    (3, {"days_past_due": 1}, "escalate", "P07", "risk_flag"),
    (3, {"fraud_flag": True}, "escalate", "P07", "risk_flag"),
    (3, {"customer_status": "Suspended"}, "escalate", "P07", "risk_flag"),
    (4, {"scopes": ["customer:read"]}, "escalate", None, "out_of_scope"),
    (5, {}, "confirm", "P02", ""),
    (8, {"rules_outcome": "Revisión humana"}, "escalate", "P05", "borderline"),
    (8, {"prescore_ci_crosses_threshold": True}, "escalate", "P05", "borderline"),
]


@pytest.mark.parametrize("fila,cambios,accion,regla,reason", FILAS, ids=[f"fila{f[0]}-{'+'.join(f[1]) or 'base'}" for f in FILAS])
def test_fila_del_motor(fila, cambios, accion, regla, reason):
    r = engine.decide({**SIM, **cambios}, POL)
    assert r.api_action == accion
    if regla:
        assert regla in r.rules_fired
        assert min(r.rules_fired, key=lambda x: engine.ACTION_ORDER.index(_accion(x))) == regla  # la regla esperada es la que gana
    else:
        assert "P02" not in r.rules_fired
    assert r.reason_code == reason
    if accion != "confirm":
        assert r.allowed_tools == []  # sin confirmación no se llama ninguna tool de datos del cliente


def _accion(rid):
    return next(x["action"] for x in engine.load_policy(POL)["rules"] if x["id"] == rid)


def _pedir(rt, users, quien="cliente_co_ok"):
    from eval.amounts import catalog_amount
    r = handle(f"¿Califico para un préstamo personal de {catalog_amount(rt[0], 'CO', 'personal_loan', 'min')}?", users[quien], rt=rt)
    assert r["action"] == "confirm" and r.get("action_id")
    return r


def test_fila6_sin_consentimiento_no_usa_datos(rt, users, deps):
    r = _pedir(rt, users)
    r2 = confirm(r["action_id"], False, {"customer_id": users["cliente_co_ok"]["customer_id"]}, rt=rt)
    assert r2["action"] == "answer" and r2["reply"].startswith("Entendido") and r2["citations"] == []
    assert "Resultado preliminar" not in r2["reply"]


def test_fila7_con_consentimiento_da_resultado(rt, users):
    r = _pedir(rt, users)
    r2 = confirm(r["action_id"], True, {"customer_id": users["cliente_co_ok"]["customer_id"]}, rt=rt)
    assert r2["action"] == "answer" and "Resultado preliminar: Elegible" in r2["reply"]
