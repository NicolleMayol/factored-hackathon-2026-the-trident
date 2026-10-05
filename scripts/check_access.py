"""Checks de acceso a los recursos reales (plan it. 3, A1–A7). Imprime ok / cold / down por recurso y el error exacto.

    python scripts/check_access.py             # todos
    python scripts/check_access.py A1 A3 A4    # algunos

Credenciales solo desde .env / entorno o el perfil de la CLI (nunca en el repo), ver agent/adapters/dbx_auth.py:
  local:  databricks auth login --host https://adb-xxxx.azuredatabricks.net --profile fh26   +   DATABRICKS_CONFIG_PROFILE=fh26
  Azure:  DATABRICKS_HOST + DATABRICKS_CLIENT_ID + DATABRICKS_CLIENT_SECRET (sp-agent-ro, OAuth M2M)
  SQL_HTTP_PATH, FM_ENDPOINT_MAIN, FM_ENDPOINT_SMALL, PRESCORE_ENDPOINT, EMBED_ENDPOINT, MLFLOW_EXPERIMENT, COSMOS_ENDPOINT, COSMOS_KEY, FUNCTION_URL
"""
from __future__ import annotations
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import requests  # noqa: E402

try:
    from dotenv import load_dotenv  # opcional
    load_dotenv(ROOT / ".env")
except Exception:
    for line in (ROOT / ".env").read_text().splitlines() if (ROOT / ".env").exists() else []:
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.strip())

from agent.adapters import dbx_auth  # noqa: E402

HOST = dbx_auth.host()
E = os.environ.get


def H():
    return {**dbx_auth.auth_headers(), "Content-Type": "application/json"}


def a1_workspace():
    me = requests.get(f"{HOST}/api/2.0/preview/scim/v2/Me", headers=H(), timeout=15); me.raise_for_status()
    sch = requests.get(f"{HOST}/api/2.1/unity-catalog/schemas", headers=H(), params={"catalog_name": "hackathon"}, timeout=15); sch.raise_for_status()
    names = sorted(s["name"] for s in sch.json().get("schemas", []))
    tabs = requests.get(f"{HOST}/api/2.1/unity-catalog/tables", headers=H(), params={"catalog_name": "hackathon", "schema_name": "gold"}, timeout=15)
    gold = sorted(t["name"] for t in tabs.json().get("tables", [])) if tabs.ok else []
    return "ok", f"usuario={me.json().get('userName')} esquemas={names} gold={gold or 'sin tablas aún (E1)'}"


def a2_sql():
    path = E("SQL_HTTP_PATH")
    if not path:
        return "down", "falta SQL_HTTP_PATH (N2)"
    wid = path.rstrip("/").split("/")[-1]
    st = requests.get(f"{HOST}/api/2.0/sql/warehouses/{wid}", headers=H(), timeout=15); st.raise_for_status()
    state = st.json().get("state")
    t0 = time.time()
    r = requests.post(f"{HOST}/api/2.0/sql/statements", headers=H(), json={"warehouse_id": wid, "statement": "SELECT 1", "wait_timeout": "30s"}, timeout=60)
    r.raise_for_status(); dt = round(time.time() - t0, 1)
    ok = r.json().get("status", {}).get("state") == "SUCCEEDED"
    detail = f"estado={state} SELECT 1 en {dt}s"
    if ok:  # lectura real de gold con el adaptador del agente
        from agent.adapters.sql_warehouse import SQLWarehouse
        from agent.config.settings import Settings
        q = SQLWarehouse(Settings())
        prof = q.query("customer_profile", {"customer_id": "TEST-CO-001"})
        rates = q.query("regulator_rates", {"country": "CO"})
        detail += f" · customer_360 TEST-CO-001={'ok' if prof else 'SIN FILA (E1)'} ({q.last_ms} ms) · regulator_rates CO={len(rates)} filas"
    return ("ok" if state == "RUNNING" else "cold") if ok else "down", detail


def _chat(endpoint: str):
    t0 = time.time()
    r = requests.post(f"{HOST}/serving-endpoints/{endpoint}/invocations", headers=H(), timeout=60,
                      json={"messages": [{"role": "user", "content": 'Responde solo con JSON: {"ok": true}'}], "max_tokens": 20, "temperature": 0})
    r.raise_for_status(); j = r.json()
    return round(time.time() - t0, 2), j.get("choices", [{}])[0].get("message", {}).get("content", "")[:60], j.get("usage", {})


def a3_fm_apis():
    out = []
    for name in (E("FM_ENDPOINT_SMALL", "databricks-meta-llama-3-1-8b-instruct"), E("FM_ENDPOINT_MAIN", "databricks-meta-llama-3-3-70b-instruct")):
        dt, txt, usage = _chat(name); out.append(f"{name}: {dt}s tokens={usage.get('total_tokens')} → {txt!r}")
    return "ok", " | ".join(out)


def a4_mlflow():
    exp = E("MLFLOW_EXPERIMENT", "/Shared/fh26/agente")
    r = requests.get(f"{HOST}/api/2.0/mlflow/experiments/get-by-name", headers=H(), params={"experiment_name": exp}, timeout=15); r.raise_for_status()
    eid = r.json()["experiment"]["experiment_id"]
    run = requests.post(f"{HOST}/api/2.0/mlflow/runs/create", headers=H(), json={"experiment_id": eid, "run_name": "check_access", "tags": [{"key": "check", "value": "A4"}]}, timeout=15); run.raise_for_status()
    rid = run.json()["run"]["info"]["run_id"]
    requests.post(f"{HOST}/api/2.0/mlflow/runs/update", headers=H(), json={"run_id": rid, "status": "FINISHED"}, timeout=15)
    return "ok", f"experimento={eid} run={rid[:8]} (puedes borrarlo)"


def a5_serving():
    out, status = [], "ok"
    for name in (E("PRESCORE_ENDPOINT", "prescore-lgbm"), E("EMBED_ENDPOINT", "embed-bge-m3")):
        r = requests.get(f"{HOST}/api/2.0/serving-endpoints/{name}", headers=H(), timeout=15)
        if r.status_code == 404:
            out.append(f"{name}: no existe (N9)"); status = "down"; continue
        r.raise_for_status(); st = r.json().get("state", {})
        s = "ok" if st.get("ready") == "READY" and st.get("config_update") == "NOT_UPDATING" else "cold"
        out.append(f"{name}: ready={st.get('ready')} scale_to_zero={r.json().get('config', {}).get('served_entities', [{}])[0].get('scale_to_zero_enabled')}")
        status = s if status == "ok" else status
    return status, " | ".join(out)


def a6_cosmos():
    ep, key = E("COSMOS_ENDPOINT"), E("COSMOS_KEY")
    if not (ep and key):
        return "down", "faltan COSMOS_ENDPOINT / COSMOS_KEY (N3)"
    from azure.cosmos import CosmosClient
    db = CosmosClient(ep, key).get_database_client("agent")
    names = [c["id"] for c in db.list_containers()]
    n = db.get_container_client("policy_chunks").query_items("SELECT VALUE COUNT(1) FROM c", enable_cross_partition_query=True)
    cnt = next(iter(n), 0)
    h = db.get_container_client("handoffs"); doc = {"id": "check-access", "case_id": "check-access", "ts": time.time()}
    h.upsert_item(doc); h.delete_item("check-access", partition_key="check-access")
    return "ok", f"contenedores={names} policy_chunks={cnt} docs; handoffs escritura/borrado ok"


def a7_function():
    url = E("FUNCTION_URL")
    if not url:
        return "down", "falta FUNCTION_URL (deploy.yml, N10)"
    r = requests.get(f"{url.rstrip('/')}/healthz", timeout=30)
    return ("ok" if r.status_code == 200 else "cold" if r.status_code == 503 else "down"), f"{r.status_code} {r.text[:120]}"


CHECKS = {"A1": ("workspace + Unity Catalog", a1_workspace), "A2": ("SQL Warehouse wh-agent", a2_sql), "A3": ("FM APIs small + main", a3_fm_apis),
          "A4": ("MLflow experimento", a4_mlflow), "A5": ("Model Serving prescore-lgbm / embed-bge-m3", a5_serving), "A6": ("Cosmos DB", a6_cosmos), "A7": ("Function App /healthz", a7_function)}

if __name__ == "__main__":
    wanted = sys.argv[1:] or list(CHECKS)
    if not HOST:
        print("sin host: pon DATABRICKS_HOST en .env o DATABRICKS_CONFIG_PROFILE con un perfil de `databricks auth login`"); sys.exit(2)
    print(f"host={HOST} auth={dbx_auth.mode()}")
    worst = 0
    for k in wanted:
        label, fn = CHECKS[k]
        try:
            status, detail = fn()
        except Exception as e:  # noqa: BLE001
            status, detail = "down", f"{type(e).__name__}: {str(e)[:200]}"
        worst = max(worst, {"ok": 0, "cold": 1, "down": 2}[status])
        print(f"{k} {status:<5} {label:<42} {detail}")
    sys.exit(worst)
