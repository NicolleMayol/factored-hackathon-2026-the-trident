"""P06: un slot obligatorio devuelto por el LLM como null cuenta como faltante → clarify, no confirm (hallazgo del eval real, 5 oct)."""
from agent.graph import nodes


def test_slot_null_es_faltante():
    assert any(not ({"product_type": None}).get(k) for k in nodes.REQUIRED_SLOTS["eligibility_simulation"])
    assert not any(not ({"product_type": "personal_loan"}).get(k) for k in nodes.REQUIRED_SLOTS["eligibility_simulation"])


def test_califico_sin_producto_pide_aclaracion(rt, users):
    """Con el LLM mock el mensaje ambiguo ya daba clarify; este test fija que un slots={'product_type': None} también lo da."""
    from agent.handle import handle
    r = handle("¿Califico?", users["cliente_co_ok"], rt=rt)
    assert r["action"] == "clarify" and "P06" in r["_state"]["rules_fired"]
