"""SQL mock: lee CSV de data/mock con el esquema de contracts/gold.yaml. Misma firma que sql_warehouse."""
from __future__ import annotations
import csv
from functools import lru_cache
from pathlib import Path
from typing import Any

QUERIES = {
    "customer_profile": ("customer_360.csv", "customer_id"),
    "customer_products": ("customer_products.csv", "customer_id"),
    "customer_behavior": ("customer_behavior_12m.csv", "customer_id"),
    "regulator_rates": ("regulator_rates.csv", "country"),
    "product_catalog": ("credit_product_catalog.csv", "country"),
}


class SQLCsv:
    def __init__(self, settings):
        self.dir: Path = Path(settings.mock_dir)

    @lru_cache(maxsize=16)
    def _load(self, name: str) -> tuple[dict[str, Any], ...]:
        with open(self.dir / name, newline="", encoding="utf-8") as f:
            return tuple(dict(r) for r in csv.DictReader(f))

    def query(self, name: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        fname, key = QUERIES[name]
        rows = self._load(fname)
        val = params.get(key)
        out = [r for r in rows if val is None or r.get(key) == val]
        for extra in ("product_type",):
            if params.get(extra):
                out = [r for r in out if r.get(extra) == params[extra]]
        return [_typed(r) for r in out]


def _typed(r: dict[str, Any]) -> dict[str, Any]:
    o = {}
    for k, v in r.items():
        if v is None or v == "":
            o[k] = None
            continue
        try:
            o[k] = int(v) if v.lstrip("-").isdigit() else float(v) if _isfloat(v) else (v == "true" if v in ("true", "false") else v)
        except Exception:
            o[k] = v
    return o


def _isfloat(v: str) -> bool:
    try:
        float(v); return "." in v
    except ValueError:
        return False
