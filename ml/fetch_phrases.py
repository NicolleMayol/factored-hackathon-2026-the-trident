"""M5 · Extrae las frases plantilla distintas de customer_text (silver.call_transcripts) a data/ref/customer_text_phrases.csv, IGNORADO por git:
las filas del dataset no salen del workspace (ADR-12, revisión #51). El etiquetado (ml/label_phrases.py) corre en local o en un notebook de
Databricks; lo que entra al repo es la regla (docs/labels.md: overrides por prefijo + modelo), no las frases. E3 aplica la misma regla en el pipeline.

    python ml/fetch_phrases.py
"""
from __future__ import annotations
import csv
import os
import sys
import time
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
try:
    from dotenv import load_dotenv; load_dotenv(ROOT / ".env")
except Exception:  # noqa: BLE001
    pass
from agent.adapters import dbx_auth  # noqa: E402

HOST = dbx_auth.host(); WID = os.environ["SQL_HTTP_PATH"].rstrip("/").split("/")[-1]


def run(sql: str):
    r = requests.post(f"{HOST}/api/2.0/sql/statements", headers={**dbx_auth.auth_headers(), "Content-Type": "application/json"},
                      json={"warehouse_id": WID, "statement": sql, "wait_timeout": "50s", "on_wait_timeout": "CONTINUE", "row_limit": 1000}, timeout=70)
    j = r.json(); sid = j.get("statement_id")
    while j.get("status", {}).get("state") in ("PENDING", "RUNNING"):
        time.sleep(3); j = requests.get(f"{HOST}/api/2.0/sql/statements/{sid}", headers=dbx_auth.auth_headers(), timeout=30).json()
    return j


for table in ("hackathon.silver.call_transcripts", "hackathon.bronze.call_transcripts"):
    j = run(f"SELECT customer_text, COUNT(*) AS n FROM {table} WHERE customer_text IS NOT NULL GROUP BY customer_text ORDER BY n DESC")
    st = j.get("status", {})
    if st.get("state") == "SUCCEEDED":
        rows = j["result"].get("data_array", [])
        out = ROOT / "data" / "ref" / "customer_text_phrases.csv"; out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f); w.writerow(["customer_text", "n"]); w.writerows(rows)
        print(f"{len(rows)} frases distintas desde {table} → {out}")
        for t, n in rows[:5]:
            print(f"  {n:>7} · {t[:80]}")
        break
    msg = st.get("error", {}).get("message", st)
    print(f"{table}: {str(msg)[:200]}")
else:
    print("Sin acceso: pide a Nicolle `GRANT USE SCHEMA, SELECT ON SCHEMA hackathon.silver TO <tu usuario>` (o que corra ella la consulta y te pase el CSV).")
