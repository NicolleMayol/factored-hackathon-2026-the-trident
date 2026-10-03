"""Mock de `gold.contact_demand` con el vocabulario real del dataset (E4).

    python data/ref/build_contact_demand_mock.py     # escribe data/mock/contact_demand.csv

El mock anterior usaba `reason_category` ∈ {credit, card, payment}, que no existe en el origen: las
categorías reales son Transaccional, Producto, Queja, Técnico, Comercial y Retención. Ninguna tool
del agente lee esta tabla —alimenta el notebook de insights (E10) y el pitch—, pero un mock con un
vocabulario inventado hace que cualquiera que lo mire saque conclusiones sobre categorías que no
existen.

Los valores son **sintéticos y deterministas**, no agregados del dataset: ningún dato de Factored
entra al repo. Las proporciones replican lo medido el 2026-10-03 sobre 686.296 interacciones, para
que el mock se parezca a la tabla real en forma y en orden de magnitud.
"""
from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SALIDA = ROOT / "data" / "mock" / "contact_demand.csv"

PAISES = ("Mexico", "Colombia", "Argentina")

# reason_category → (peso del volumen, FCR, tasa de escalamiento, espera p50 en s, CSAT medio).
# Medido: Queja y Técnico son las que peor resuelven y más escalan; Transaccional domina el volumen.
PERFIL = {
    "Transaccional": (0.350, 0.91, 0.05, 110, 2.9),
    "Producto":      (0.220, 0.92, 0.06, 118, 3.2),
    "Queja":         (0.171, 0.43, 0.24, 126, 2.5),
    "Técnico":       (0.150, 0.55, 0.19, 141, 2.1),
    "Comercial":     (0.080, 0.78, 0.09, 105, 2.8),
    "Retención":     (0.030, 0.52, 0.14, 132, 2.3),
}
VOLUMEN_DIARIO_POR_PAIS = 210  # 686.296 interacciones / 1.097 días / 3 países
DIAS = 7
DESDE = dt.date(2025, 6, 1)


def main() -> int:
    filas = []
    for i in range(DIAS):
        fecha = DESDE + dt.timedelta(days=i)
        for pais in PAISES:
            for cat, (peso, fcr, esc, espera, csat) in PERFIL.items():
                # Variación determinista por día y país: el mock no es plano, pero es reproducible.
                giro = ((i * 7 + len(pais) + len(cat)) % 11 - 5) / 100
                volumen = max(1, round(VOLUMEN_DIARIO_POR_PAIS * peso * (1 + giro)))
                filas.append([
                    fecha.isoformat(), pais, cat, volumen,
                    f"{min(1.0, max(0.0, fcr + giro)):.4f}",
                    round(volumen * esc),
                    round(espera * (1 + giro)),
                    f"{csat + giro:.2f}",
                ])
    with SALIDA.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "country", "reason_category", "volume", "fcr_rate", "escalated", "wait_p50_s", "csat_avg"])
        w.writerows(filas)
    print(f"{SALIDA.relative_to(ROOT)}: {len(filas)} filas · {DIAS} días × {len(PAISES)} países × {len(PERFIL)} categorías")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
