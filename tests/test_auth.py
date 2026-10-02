import time
import jwt
import pytest
from agent.auth import AuthError, decode_token, issue_test_token, require_scope

KEY = "k"


def test_token_valido():
    c = decode_token(issue_test_token("TEST-CO-001", ["customer:read"], KEY), KEY)
    assert c["customer_id"] == "TEST-CO-001"


def test_expirado_401():
    tok = jwt.encode({"customer_id": "x", "scopes": [], "exp": int(time.time()) - 10}, KEY, algorithm="HS256")
    with pytest.raises(AuthError) as e:
        decode_token(tok, KEY)
    assert e.value.status == 401 and e.value.code == "expired"


def test_firma_invalida_401():
    with pytest.raises(AuthError) as e:
        decode_token(issue_test_token("x", [], "otra"), KEY)
    assert e.value.status == 401


def test_sin_scope_403():
    c = decode_token(issue_test_token("x", ["customer:read"], KEY), KEY)
    with pytest.raises(AuthError) as e:
        require_scope(c, "handoff:read")
    assert e.value.status == 403
