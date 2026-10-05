"""Elige en gold un cliente real por cada usuario del dev set, con las mismas condiciones que el fixture TEST-*.

    python eval/pick_users.py            # escribe eval/users_gold.json (determinista: ORDER BY customer_id)
    AGENT_SQL=real python eval/run_eval.py --pause 2     # agent.cli.USERS toma los ids de ese json cuando AGENT_SQL=real

Por qué: los TEST-* de gold no tienen productos ni comportamiento (ver scripts/seed_test_customers.py), así que con SQL real
los pares de escalación por riesgo (P07) no disparan. Con clientes reales elegidos por condición el dev set mide lo mismo que
con el fixture, pero sobre gold. El json guarda solo el id y la condición que lo eligió, no datos del cliente.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent.config.settings import Settings  # noqa: E402
from agent.adapters.sql_warehouse import SQLWarehouse  # noqa: E402

BASE = """SELECT c.customer_id FROM hackathon.gold.customer_360 c
JOIN hackathon.gold.customer_behavior_12m b USING (customer_id)
WHERE c.customer_status = 'Active' AND c.estimated_monthly_income IS NOT NULL AND c.credit_score IS NOT NULL AND {cond}
ORDER BY c.customer_id LIMIT 1"""
HAS = "EXISTS (SELECT 1 FROM hackathon.gold.customer_products p WHERE p.customer_id = c.customer_id AND {p})"
CARD = "p.product_type IN ('credit_card', 'Tarjeta Crédito')"       # gold usa el vocabulario del dataset (puente product_type_dataset)
LOAN = "p.product_type IN ('personal_loan', 'Préstamo Personal')"
NO_DPD = "NOT EXISTS (SELECT 1 FROM hackathon.gold.customer_products p WHERE p.customer_id = c.customer_id AND p.days_past_due > 0)"
CONDITIONS = {  # misma lectura que data/mock/customer_360.csv + customer_products.csv
    "cliente_co_ok": f"c.country_code = 'CO' AND c.credit_score >= 750 AND b.max_days_past_due = 0 AND {NO_DPD} AND " + HAS.format(p=f"{CARD} AND p.product_status = 'Active'"),
    "cliente_mx_cond": f"c.country_code = 'MX' AND c.credit_score BETWEEN 640 AND 660 AND b.max_days_past_due = 0 AND {NO_DPD} AND " + HAS.format(p="p.product_status = 'Active'"),
    "cliente_ar_no": "c.country_code = 'AR' AND c.credit_score < 600 AND " + HAS.format(p="p.days_past_due BETWEEN 31 AND 90 AND p.product_status = 'Active'"),
    "cliente_co_pt": f"c.country_code = 'CO' AND c.credit_score >= 750 AND b.max_days_past_due = 0 AND {NO_DPD} AND " + HAS.format(p=f"{LOAN} AND p.product_status = 'Active'"),
    "cliente_solo_lectura": f"c.country_code = 'MX' AND c.credit_score BETWEEN 690 AND 710 AND b.max_days_past_due = 0 AND {NO_DPD} AND " + HAS.format(p=f"{CARD} AND p.product_status = 'Active'"),
}


def main():
    q = SQLWarehouse(Settings())
    out = {}
    for alias, cond in CONDITIONS.items():
        rows = q._execute(BASE.format(cond=cond), [])
        if not rows:
            raise SystemExit(f"{alias}: ningún cliente en gold cumple: {cond}")
        out[alias] = {"customer_id": rows[0]["customer_id"], "picked_by": cond}
        print(f"{alias:22} → {rows[0]['customer_id']}")
    (ROOT / "eval" / "users_gold.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print("escrito eval/users_gold.json")


if __name__ == "__main__":
    main()
