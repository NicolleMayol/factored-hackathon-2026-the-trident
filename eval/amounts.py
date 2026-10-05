"""Los montos de los casos salen del catálogo, no de cifras fijas: {{amount:<product_type>}} → punto medio del rango del país del usuario.
Así el dev set sigue válido cuando E5 cambia pisos y techos (ADR-24)."""
from __future__ import annotations
import re
from agent.policy.engine import load_catalog

TOKEN = re.compile(r"\{\{amount:([a-z_]+)(?::(min|mid|max))?\}\}")
COUNTRY_OF_ID = {"CO": "CO", "MX": "MX", "AR": "AR"}


def catalog_amount(settings, country: str, product_type: str, which: str = "mid") -> int:
    for p in load_catalog(str(settings.catalog_path)):
        if p["country"] == country and p["product_type"] == product_type:
            lo, hi = float(p["amount_min"]), float(p["amount_max"])
            return int({"min": lo, "max": hi, "mid": (lo + hi) / 2}[which])
    raise KeyError(f"sin producto {product_type} en {country}")


def resolve_amounts(message: str, user: dict, settings) -> str:
    cid = user.get("customer_id", "")
    country = COUNTRY_OF_ID.get(cid.split("-")[1] if cid.startswith("TEST-") and "-" in cid else "", "CO")
    return TOKEN.sub(lambda m: str(catalog_amount(settings, country, m.group(1), m.group(2) or "mid")), message)
