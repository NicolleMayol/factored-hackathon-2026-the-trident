"""E6 · construye el snapshot versionado de `ref.regulator_rates` (ADR-12).

    python data/ref/ingest_regulator_rates.py            # escribe data/ref/regulator_rates_<fecha>.csv

ADR-12: ninguna fuente se consulta en vivo. Este script se corre a mano, deja un CSV versionado en
el repo, y `bundles.yml` lo copia al volumen `hackathon.ref.fuentes`; el pipeline lee el snapshot,
nunca la API. Así la respuesta del agente cita una cifra reproducible y fechada.

Grano: país × product_type × rate_kind × snapshot (ADR-22 + decisión de ia-ml en el PR #23).
`rate_kind` ∈ {ea, tna, cat, cft, usura}; `usura`/`cat`/`cft` son el techo del país.

Estado de las fuentes (2026-10-02):
  AR · BCRA        automático; API pública sin auth, tres endpoints
  CO · SFC         manual; la certificación de usura es un PDF mensual
  MX · Banxico     manual; el cuadro CF303 se exporta tras una consulta interactiva
Las filas manuales viven en FILAS_MANUALES con `source = PENDIENTE` hasta que alguien las complete;
un check de DQ falla mientras quede alguna, para que la deuda no se vuelva invisible.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import sys
import urllib.request
from pathlib import Path

BCRA = "https://api.bcra.gob.ar/transparencia/v1.0"
# El manual oficial (regimen-transparencia-v1.pdf) nombra los endpoints así. La URL que traía
# ADR-12 (`prestamosPersonales`) devuelve 404: el recurso es `Prestamos/Personales`.
ENDPOINTS = {
    "personal_loan": ("Prestamos/Personales", "tasaEfectivaAnualMaxima", "costoFinancieroEfectivoTotalMaximo"),
    "mortgage": ("Prestamos/Hipotecarios", "tasaEfectivaAnualMaxima", "costoFinancieroEfectivoTotalMaximo"),
    "credit_card": ("TarjetasCredito", "tasaEfectivaAnualMaximaFinanciacion", None),
}

# Las entidades informan en fechas que van de 2019 a hoy: un snapshot ingenuo mezclaría tasas de
# hace siete años con las de ayer. Solo entra lo informado en los últimos meses.
ANTIGUEDAD_MAX_DIAS = 120
# El régimen publica algún valor absurdo (se vieron TEA de 1.191 % y 1.230 %). Se descarta por
# arriba para que no arrastre el percentil 90.
TECHO_PLAUSIBLE = 500.0

URL_DOC = {
    "personal_loan": f"{BCRA}/Prestamos/Personales",
    "mortgage": f"{BCRA}/Prestamos/Hipotecarios",
    "credit_card": f"{BCRA}/TarjetasCredito",
}

# Filas que no se pueden automatizar hoy. Completar valor, source, url y snapshot_date; en cuanto
# `source` deje de ser PENDIENTE, el check de DQ pasa.
FILAS_MANUALES = [
    # country, product_type, rate_kind, rate_min, rate_max, source, url, snapshot_date
    ("CO", "personal_loan", "usura", "", "", "PENDIENTE",
     "https://www.superfinanciera.gov.co/publicaciones/10116142/superfinanciera-certifica-el-interes-bancario-corriente/", ""),
    ("CO", "credit_card", "usura", "", "", "PENDIENTE",
     "https://www.superfinanciera.gov.co/publicaciones/10116142/superfinanciera-certifica-el-interes-bancario-corriente/", ""),
    ("CO", "mortgage", "usura", "", "", "PENDIENTE",
     "https://www.superfinanciera.gov.co/publicaciones/10116142/superfinanciera-certifica-el-interes-bancario-corriente/", ""),
    ("MX", "personal_loan", "cat", "", "", "PENDIENTE",
     "https://www.banxico.org.mx/SieInternet/consultarDirectorioInternetAction.do?sector=18&accion=consultarCuadro&idCuadro=CF303&locale=es", ""),
    ("MX", "credit_card", "cat", "", "", "PENDIENTE",
     "https://www.banxico.org.mx/SieInternet/consultarDirectorioInternetAction.do?sector=18&accion=consultarCuadro&idCuadro=CF303&locale=es", ""),
    ("MX", "mortgage", "cat", "", "", "PENDIENTE",
     "https://www.banxico.org.mx/SieInternet/consultarDirectorioInternetAction.do?sector=18&accion=consultarCuadro&idCuadro=CF303&locale=es", ""),
]

CABECERA = ["country", "product_type", "rate_kind", "rate_min", "rate_max", "source", "url", "snapshot_date"]


def _get(path: str) -> list[dict]:
    req = urllib.request.Request(f"{BCRA}/{path}", headers={"User-Agent": "fh26-ingest/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)["results"]


def _percentil(valores: list[float], q: float) -> float:
    v = sorted(valores)
    return v[max(0, min(len(v) - 1, round(q * (len(v) - 1))))]


def _rango(registros: list[dict], campo: str, corte: dt.date) -> tuple[float, float, int] | None:
    """p10 y p90 de un campo, sobre lo informado desde `corte` y dentro de lo plausible."""
    vals = [
        r[campo] for r in registros
        if isinstance(r.get(campo), (int, float)) and 0 < r[campo] <= TECHO_PLAUSIBLE
        and (r.get("fechaInformacion") or "") >= corte.isoformat()
    ]
    if len(vals) < 10:  # con menos entidades el percentil no dice nada
        return None
    return _percentil(vals, 0.10), _percentil(vals, 0.90), len(vals)


def construir(hoy: dt.date) -> list[list]:
    corte = hoy - dt.timedelta(days=ANTIGUEDAD_MAX_DIAS)
    filas: list[list] = []
    for product_type, (path, campo_tasa, campo_cft) in ENDPOINTS.items():
        registros = _get(path)
        fecha = max((r.get("fechaInformacion") or "") for r in registros) or hoy.isoformat()
        # `ea`: tasa de mercado. El BCRA publica tasa efectiva anual, no nominal, así que el
        # rate_kind es `ea` y no `tna` como suponía el mock de ia-ml.
        r_ea = _rango(registros, campo_tasa, corte)
        if r_ea:
            lo, hi, n = r_ea
            filas.append(["AR", product_type, "ea", f"{lo:.2f}", f"{hi:.2f}",
                          f"BCRA Régimen de Transparencia (n={n})", URL_DOC[product_type], fecha])
        # `cft`: techo del país en AR (Com. A 5460). Solo lo publican préstamos, no tarjetas.
        if campo_cft:
            r_cft = _rango(registros, campo_cft, corte)
            if r_cft:
                lo, hi, n = r_cft
                filas.append(["AR", product_type, "cft", f"{lo:.2f}", f"{hi:.2f}",
                              f"BCRA Régimen de Transparencia (n={n})", URL_DOC[product_type], fecha])
    filas.extend([list(f) for f in FILAS_MANUALES])
    return filas


def main() -> int:
    hoy = dt.date.today()
    filas = construir(hoy)
    destino = Path(__file__).resolve().parent / f"regulator_rates_{hoy.isoformat()}.csv"
    with destino.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(CABECERA)
        w.writerows(filas)
    pendientes = [f for f in filas if f[5] == "PENDIENTE"]
    print(f"{destino.name}: {len(filas)} filas, {len(filas) - len(pendientes)} con fuente real, {len(pendientes)} PENDIENTE")
    for f in filas:
        marca = "  " if f[5] != "PENDIENTE" else "! "
        print(f"  {marca}{f[0]} {f[1]:<14} {f[2]:<6} {f[3]:>8} - {f[4]:<8} {f[5][:46]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
