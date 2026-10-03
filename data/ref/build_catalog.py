"""E5 · genera `policy/catalog.yaml`, el catálogo sintético de productos de crédito.

    python data/ref/build_catalog.py        # escribe policy/catalog.yaml

ADR-12 lo define como "productos plausibles por país cruzando percentiles del dataset con rangos
regulatorios", y `es_sintetico = true`: no es la oferta de un banco real.

De dónde sale cada cifra (decisión del 2026-10-02):
  AR  del BCRA, Régimen de Transparencia, lo informado en los últimos 120 días. Hay fuente pública
      con montos, plazos e ingreso mínimo reales, así que es más defendible que un percentil.
  CO  percentiles de `credit_limit` del dataset, en COP (la moneda dominante del país).
  MX  ídem, en USD: el dataset no tiene un solo producto en MXN (ADR-23).

Las tasas del catálogo son la oferta; el techo legal vive en `ref.regulator_rates` (E6) y el motor
lo aplica aparte. Para AR se usa p10–mediana del BCRA: el p90 (337 %) es la cola del mercado, no
una tasa que este banco ofrecería.

`product_type_dataset` es la llave de join con `gold.customer_products`, que trae los valores en
español del origen. Sin esa columna, `evaluate_eligibility` no encuentra el producto del cliente
y devuelve cero sin error (mismo patrón que `country_code`).
"""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SALIDA = ROOT / "policy" / "catalog.yaml"
VIGENCIA = ("2025-07-01", "2026-12-31")

# Percentiles de credit_limit del dataset, por país y producto, en la moneda dominante.
# Consulta que los produjo (wh-agent, 2026-10-02):
#   SELECT c.country, p.product_type, p.currency,
#          percentile(p.credit_limit, 0.10), percentile(p.credit_limit, 0.90),
#          percentile(p.interest_rate, 0.10), percentile(p.interest_rate, 0.90)
#   FROM products p JOIN customers c USING (customer_id)
#   WHERE p.credit_limit IS NOT NULL GROUP BY 1,2,3
DATASET = {
    ("CO", "personal_loan"): dict(monto=(75_534_925, 542_588_089), tasa=(13.62, 26.28)),
    ("CO", "credit_card"):   dict(monto=(23_405_438, 180_283_078), tasa=(20.66, 42.33)),
    ("CO", "mortgage"):      dict(monto=(76_519_585, 539_420_007), tasa=(6.56, 11.41)),
    ("MX", "personal_loan"): dict(monto=(20_311, 135_395), tasa=(13.54, 26.50)),
    ("MX", "credit_card"):   dict(monto=(5_911, 45_210), tasa=(20.69, 42.34)),
    ("MX", "mortgage"):      dict(monto=(19_786, 134_138), tasa=(6.58, 11.41)),
}

# BCRA, lo informado en los últimos 120 días (data/ref/ingest_regulator_rates.py usa la misma API).
BCRA = {
    ("AR", "personal_loan"): dict(monto=(450_000, 40_000_000), tasa=(66.00, 132.05), plazo=60, ingreso=50_000),
    ("AR", "credit_card"):   dict(monto=(2_069_104, 15_809_487), tasa=(61.67, 116.76), plazo=36, ingreso=391_200),
    ("AR", "mortgage"):      dict(monto=(300_000_000, 372_113_275), tasa=(7.76, 14.00), plazo=240, ingreso=3_500_000),
}

# Piso de producto: el monto mínimo que el banco presta, no el p10 de los saldos existentes.
# El p10 de credit_limit es la distribución de cupos ya otorgados; usarlo como mínimo dejaba
# CO-PL en 75 M COP y mandaba cualquier préstamo pequeño a E07 (revisión de ia-ml en el PR #31).
PISO = {"COP": 500_000, "USD": 150, "ARS": 50_000}
PISO_HIPOTECARIO = 100  # el hipotecario no arranca en el mismo piso que un consumo: × este factor

# Techo del país por rate_kind (engine.py CAP_KIND). El catálogo nunca puede ofrecer por encima:
# si lo hace, E11 manda toda simulación del país a revisión humana.
CAP_KIND = {"CO": "usura", "MX": "cat", "AR": "cft"}

MONEDA = {"CO": "COP", "MX": "USD", "AR": "ARS"}  # MX en USD: el dataset no tiene MXN (ADR-23)
PAIS_NOMBRE = {"CO": "Colombia", "MX": "México", "AR": "Argentina"}

# Taxonomía del catálogo → valor literal de gold.customer_products. Los tres últimos no existen en
# el dataset: son oferta sin cartera, y se declaran con product_type_dataset vacío.
TIPOS = [
    # codigo, product_type,          product_type_dataset,   name_es,                name_pt,                  plazo, min_score
    ("PL-01",  "personal_loan",       "Préstamo Personal",    "Préstamo personal",    "Empréstimo pessoal",      60, 600),
    ("CC-02",  "credit_card",         "Tarjeta Crédito",      "Tarjeta de crédito",   "Cartão de crédito",       36, 600),
    ("MG-06",  "mortgage",            "Préstamo Hipotecario", "Crédito hipotecario",  "Crédito habitacional",   240, 680),
    ("PRL-03", "payroll_loan",        None,                   "Crédito de libranza",  "Crédito consignado",      72, 580),
    ("LAC-04", "low_amount_consumer", None,                   "Crédito de bajo monto", "Crédito de baixo valor", 24, 550),
    ("MC-05",  "microcredit",         None,                   "Microcrédito",         "Microcrédito",            36, 540),
]

REQUISITOS = {
    "personal_loan": "mayor de edad; ingreso demostrable; sin mora > 30 días",
    "credit_card": "mayor de edad; ingreso demostrable; sin mora > 30 días",
    "mortgage": "mayor de edad; ingreso demostrable; sin mora > 30 días; avalúo del inmueble; cuota ≤ 30 % del ingreso",
    "payroll_loan": "relación laboral vigente; convenio de nómina con el empleador",
    "low_amount_consumer": "mayor de edad; ingreso demostrable",
    "microcredit": "actividad productiva declarada; mayor de edad",
}


def _derivado(base: dict, factor_monto: float, factor_tasa: float) -> dict:
    """Los tres productos sin contraparte en el dataset se derivan del préstamo personal del país.
    Se declara el factor en vez de inventar un número suelto."""
    return dict(
        monto=(round(base["monto"][0] * factor_monto), round(base["monto"][1] * factor_monto)),
        tasa=(round(base["tasa"][0] * factor_tasa, 2), round(base["tasa"][1] * factor_tasa, 2)),
    )


FACTORES = {  # (monto, tasa) respecto al préstamo personal del mismo país
    "payroll_loan": (0.80, 0.75),          # con descuento de nómina, menos riesgo y menos tasa
    "low_amount_consumer": (0.10, 1.15),   # ticket pequeño, tasa algo mayor
    "microcredit": (0.05, 1.30),           # el más caro y el más pequeño
}


def _techos() -> dict[tuple[str, str], float]:
    """rate_max del tipo de tasa que actúa como techo, por país y producto, leído del snapshot de
    E6. Es la misma fuente que usa el motor, así que no pueden discrepar."""
    import csv

    snaps = sorted((ROOT / "data" / "ref").glob("regulator_rates_*.csv"))
    if not snaps:
        return {}
    out = {}
    for f in csv.DictReader(snaps[-1].open(encoding="utf-8")):
        if f["rate_kind"] == CAP_KIND.get(f["country"]) and f["rate_max"]:
            out[(f["country"], f["product_type"])] = float(f["rate_max"])
    return out


def construir() -> dict:
    techos = _techos()
    productos = []
    for pais in ("CO", "MX", "AR"):
        fuente = BCRA if pais == "AR" else DATASET
        base = fuente[(pais, "personal_loan")]
        for codigo, ptype, pdataset, name_es, name_pt, plazo, min_score in TIPOS:
            if (pais, ptype) in fuente:
                v = fuente[(pais, ptype)]
                plazo_final = v.get("plazo", plazo)
            else:
                v = _derivado(base, *FACTORES[ptype])
                plazo_final = plazo
            # El catálogo ofrece dentro del techo legal: rate_max = min(p90, techo del país).
            tasa_max = v["tasa"][1]
            # Si no hay fila de techo para ese producto, se usa el del préstamo personal del país:
            # es de donde se derivan esos tres, y el techo varía demasiado entre productos como para
            # tomar el más estricto (el del hipotecario en AR dejaría rate_min > rate_max).
            # Hueco anotado: libranza, bajo monto y microcrédito no tienen fila en E6, así que E11
            # tampoco los protege en el motor.
            techo = techos.get((pais, ptype)) or techos.get((pais, "personal_loan"))
            recortada = techo is not None and tasa_max > techo
            if recortada:
                tasa_max = techo
            if tasa_max < v["tasa"][0]:  # el recorte no puede invertir el rango
                raise SystemExit(f"{pais}-{codigo}: techo {tasa_max} por debajo de rate_min {v['tasa'][0]}")
            piso = PISO[MONEDA[pais]] * (PISO_HIPOTECARIO if ptype == "mortgage" else 1)
            productos.append({
                "product_code": f"{pais}-{codigo}",
                "country": pais,
                "country_name": PAIS_NOMBRE[pais],
                "name_es": name_es,
                "name_pt": name_pt,
                "product_type": ptype,
                "product_type_dataset": pdataset,
                "currency": MONEDA[pais],
                "rate_min": v["tasa"][0],
                "rate_max": tasa_max,
                "amount_min": piso,
                "amount_max": v["monto"][1],
                "term_months_max": plazo_final,
                "min_score": min_score,
                "requirements": REQUISITOS[ptype],
                "valid_from": VIGENCIA[0],
                "valid_to": VIGENCIA[1],
                "es_sintetico": True,
            })
    return {
        "version": "v1",
        "generado": "data/ref/build_catalog.py (E5, 2026-10-02)",
        "note": "Catálogo sintético (ADR-12). AR del BCRA; CO y MX de percentiles del dataset. "
                "El techo legal vive en ref.regulator_rates (E6), no aquí.",
        "products": productos,
    }


def _escribir_mock(cat: dict) -> Path:
    """El mock que lee el agente con AGENT_SQL=mock se genera del mismo catálogo, con las columnas
    de contracts/gold.yaml. Generarlo en vez de mantenerlo a mano es lo que impide que el mock y la
    tabla real se separen, que es como apareció la deriva de rate_kind."""
    import csv

    cols = [c for c in yaml.safe_load((ROOT / "contracts" / "gold.yaml").read_text(encoding="utf-8"))
            ["tables"]["gold.credit_product_catalog"]["columns"]]
    destino = ROOT / "data" / "mock" / "credit_product_catalog.csv"
    with destino.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for p in cat["products"]:
            w.writerow(["" if p.get(c) is None else p.get(c, "") for c in cols])
    return destino


def main() -> int:
    techos = _techos()
    cat = construir()
    SALIDA.parent.mkdir(exist_ok=True)
    with SALIDA.open("w", encoding="utf-8") as f:
        yaml.safe_dump(cat, f, allow_unicode=True, sort_keys=False, width=200)
    mock = _escribir_mock(cat)
    print(f"{mock.relative_to(ROOT)}: regenerado con las columnas del contrato")
    con_join = sum(1 for p in cat["products"] if p["product_type_dataset"])
    print(f"{SALIDA.relative_to(ROOT)}: {len(cat['products'])} productos "
          f"({con_join} con contraparte en el dataset, {len(cat['products']) - con_join} oferta sin cartera)")
    for p in cat["products"]:
        marca = " " if p["product_type_dataset"] else "~"
        tope = techos.get((p["country"], p["product_type"]))
        nota = f"  (recortada al techo {tope})" if tope is not None and p["rate_max"] == tope else ""
        print(f"  {marca}{p['product_code']:10} {p['product_type']:20} {p['currency']} "
              f"{p['rate_min']:>7.2f}-{p['rate_max']:<7.2f} {p['amount_min']:>13,}-{p['amount_max']:<14,} {p['term_months_max']:>4}m{nota}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
