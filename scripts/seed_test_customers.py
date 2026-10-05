"""Completa los clientes de prueba TEST-* en gold (productos y comportamiento) desde data/mock/*.csv.

    python scripts/seed_test_customers.py            # dry-run: muestra qué filas faltan y el SQL
    python scripts/seed_test_customers.py --apply    # MERGE idempotente (necesita MODIFY en las dos tablas)
    python scripts/seed_test_customers.py --verify   # cuenta las filas TEST-* en gold

Por qué: el pipeline de datos cargó los TEST-* en gold.customer_360 pero no en customer_products ni customer_behavior_12m
(5 oct: 400.000 productos, 0 de prueba). Sin productos no hay mora, P07 nunca dispara y ni el dev set ni la UI pueden mostrar
una escalación por riesgo. Solo toca ids TEST-* (los mismos del fixture); nunca filas reales. Las columnas se intersectan con
las de gold (information_schema), así que un esquema con menos columnas no rompe el MERGE.
"""
from __future__ import annotations
import argparse
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent.config.settings import Settings  # noqa: E402
from agent.adapters.sql_warehouse import SQLWarehouse  # noqa: E402

TABLES = {  # tabla gold → (csv del fixture, columnas clave del MERGE)
    "customer_products": ("customer_products.csv", ["product_id"]),
    "customer_behavior_12m": ("customer_behavior_12m.csv", ["customer_id"]),
}
TYPE_MAP = {"credit_card": "Tarjeta Crédito", "personal_loan": "Préstamo Personal", "mortgage": "Préstamo Hipotecario"}  # vocabulario de gold
SAFE = re.compile(r"^[A-Za-z0-9_.:\- ÁÉÍÓÚáéíóúñÑ]+$")  # valores del fixture; nada de texto libre


def _lit(v: str, typ: str) -> str:
    if v == "" or v is None:
        return "NULL"
    if typ in ("INT", "BIGINT", "SMALLINT", "TINYINT", "LONG"):
        return str(int(float(v)))
    if typ in ("DOUBLE", "FLOAT", "DECIMAL"):
        return str(float(v))
    if typ.startswith("TIMESTAMP"):
        return f"TIMESTAMP '{v.replace('T', ' ')}'"
    if typ == "DATE":
        return f"DATE '{v[:10]}'"
    assert SAFE.match(v), f"valor inesperado en el fixture: {v!r}"
    return f"'{v}'"


def gold_columns(q: SQLWarehouse, table: str) -> dict[str, str]:
    rows = q._execute("SELECT column_name, data_type FROM hackathon.information_schema.columns WHERE table_schema = 'gold' AND table_name = :t ORDER BY ordinal_position",
                      [{"name": "t", "value": table, "type": "STRING"}])
    return {r["column_name"]: str(r["data_type"]).upper() for r in rows}


def merge_sql(table: str, cols: dict[str, str], rows: list[dict[str, str]], keys: list[str]) -> str:
    use = [c for c in rows[0] if c in cols]
    values = ",\n    ".join("(" + ", ".join(_lit(r[c], cols[c]) for c in use) + ")" for r in rows)
    on = " AND ".join(f"t.{k} = s.{k}" for k in keys)
    upd = ", ".join(f"t.{c} = s.{c}" for c in use if c not in keys)
    return (f"MERGE INTO hackathon.gold.{table} t\nUSING (VALUES\n    {values}\n) AS s({', '.join(use)})\nON {on}\n"
            f"WHEN MATCHED THEN UPDATE SET {upd}\nWHEN NOT MATCHED THEN INSERT ({', '.join(use)}) VALUES ({', '.join('s.' + c for c in use)})")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--verify", action="store_true")
    a = ap.parse_args()
    q = SQLWarehouse(Settings())
    for table, (csv_name, keys) in TABLES.items():
        n = q._execute(f"SELECT count(*) AS n FROM hackathon.gold.{table} WHERE customer_id LIKE 'TEST-%'", [])[0]["n"]
        if a.verify:
            print(f"{table}: {n} filas TEST-* en gold"); continue
        rows = [{**r, "product_type": TYPE_MAP.get(r.get("product_type", ""), r.get("product_type"))} if "product_type" in r else r
                for r in csv.DictReader(open(ROOT / "data" / "mock" / csv_name, encoding="utf-8")) if r["customer_id"].startswith("TEST-")]
        cols = gold_columns(q, table)
        missing = [c for c in rows[0] if c not in cols]
        sql = merge_sql(table, cols, rows, keys)
        print(f"{table}: {len(rows)} filas del fixture · {n} TEST-* ya en gold · columnas ignoradas: {missing or 'ninguna'}")
        if not a.apply:
            print(sql, "\n"); continue
        q._execute(sql, [])
        n2 = q._execute(f"SELECT count(*) AS n FROM hackathon.gold.{table} WHERE customer_id LIKE 'TEST-%'", [])[0]["n"]
        print(f"  MERGE ok → {n2} filas TEST-* en gold")


if __name__ == "__main__":
    main()
