"""Corre un turno en local sin Function App: python -m agent.cli cliente_co_ok "¿Cuál es la tasa del préstamo personal?" """
from __future__ import annotations
import json
import sys

from agent.handle import confirm, handle

USERS = {
    "cliente_co_ok": {"customer_id": "TEST-CO-001", "scopes": ["customer:read", "credit:simulate"], "locale": "es-CO"},
    "cliente_mx_cond": {"customer_id": "TEST-MX-002", "scopes": ["customer:read", "credit:simulate"], "locale": "es-MX"},
    "cliente_ar_no": {"customer_id": "TEST-AR-003", "scopes": ["customer:read", "credit:simulate"], "locale": "es-AR"},
    "cliente_co_pt": {"customer_id": "TEST-CO-004", "scopes": ["customer:read", "credit:simulate"], "locale": "pt-BR"},
    "cliente_solo_lectura": {"customer_id": "TEST-MX-005", "scopes": ["customer:read"], "locale": "es-MX"},
}

if __name__ == "__main__":
    user, msg = sys.argv[1], " ".join(sys.argv[2:])
    r = handle(msg, USERS[user])
    st = r.pop("_state")
    print(json.dumps({**r, "node_path": st.get("node_path"), "rules_fired": st.get("rules_fired"), "escalate_reason": st.get("escalate_reason")}, ensure_ascii=False, indent=2))
    if r.get("action_id"):
        print("--- confirmando (sí) ---")
        print(json.dumps(confirm(r["action_id"], True, {"customer_id": USERS[user]["customer_id"]}), ensure_ascii=False, indent=2))
