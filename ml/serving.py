"""Crea o actualiza endpoints de Model Serving para los modelos de ia-ml (ADR-21): scale-to-zero, CPU pequeña.

    python ml/serving.py prescore-lgbm hackathon.ml.prescore_lgbm 1      # nombre, modelo UC, versión
    python ml/serving.py embed-bge-m3  hackathon.ml.bge_m3        1 --size Medium
    python ml/serving.py --status prescore-lgbm                        # ready / not ready

Solo API (no SDK): usa las credenciales de dbx_auth (perfil local). Un endpoint con scale_to_zero no cuesta en reposo; el primer
request tras el frío tarda ~30 s (run_tool lo tolera una vez por dependencia y conversación)."""
from __future__ import annotations
import argparse
import sys
import time
from pathlib import Path
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from dotenv import load_dotenv; load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except Exception:  # noqa: BLE001
    pass
from agent.adapters import dbx_auth  # noqa: E402

HOST = dbx_auth.host()


def h():
    return {**dbx_auth.auth_headers(), "Content-Type": "application/json"}


def status(name: str) -> dict:
    r = requests.get(f"{HOST}/api/2.0/serving-endpoints/{name}", headers=h(), timeout=30)
    if r.status_code == 404:
        return {"exists": False}
    r.raise_for_status(); j = r.json(); st = j.get("state", {})
    return {"exists": True, "ready": st.get("ready"), "config_update": st.get("config_update"), "served": [e.get("entity_version") for e in j.get("config", {}).get("served_entities", [])]}


def latest_version(model: str) -> str:
    """Última versión del modelo en UC (los intentos fallidos de registro no crean versión)."""
    r = requests.get(f"{HOST}/api/2.1/unity-catalog/models/{model}/versions", headers=h(), timeout=30)
    if not r.ok:
        raise SystemExit(f"no puedo listar versiones de {model}: {r.status_code} {r.text[:200]}")
    vs = sorted(int(v["version"]) for v in r.json().get("model_versions", []))
    if not vs:
        raise SystemExit(f"{model} no tiene versiones en UC: el registro no terminó")
    return str(vs[-1])


def _fail(r, what: str):
    raise SystemExit(f"{what}: {r.status_code} {r.text[:400]}")


def upsert(name: str, model: str, version: str, size: str) -> None:
    if version in ("latest", "", None):
        version = latest_version(model)
    entity = {"entity_name": model, "entity_version": str(version), "workload_size": size, "workload_type": "CPU", "scale_to_zero_enabled": True}
    st = status(name)
    if not st["exists"]:
        body = {"name": name, "config": {"served_entities": [entity]}, "ai_gateway": {"inference_table_config": {"catalog_name": "hackathon", "schema_name": "ops", "table_name_prefix": name.replace("-", "_"), "enabled": True}}}
        r = requests.post(f"{HOST}/api/2.0/serving-endpoints", headers=h(), json=body, timeout=60)
        if not r.ok and "ai_gateway" in r.text.lower():  # inference table opcional
            body.pop("ai_gateway"); r = requests.post(f"{HOST}/api/2.0/serving-endpoints", headers=h(), json=body, timeout=60)
        if not r.ok:
            _fail(r, f"crear {name}")
        print(f"creado {name} ← {model} v{version}")
    else:
        r = requests.put(f"{HOST}/api/2.0/serving-endpoints/{name}/config", headers=h(), json={"served_entities": [entity]}, timeout=60)
        if not r.ok:
            _fail(r, f"actualizar {name}")
        print(f"actualizado {name} ← {model} v{version}")


def wait(name: str, minutes: int = 45) -> None:
    t0 = time.time()
    while time.time() - t0 < minutes * 60:
        st = status(name)
        print(f"{int(time.time() - t0)}s · ready={st.get('ready')} config_update={st.get('config_update')}", flush=True)
        if st.get("ready") == "READY" and st.get("config_update") == "NOT_UPDATING":
            return
        time.sleep(30)
    raise SystemExit(f"{name} no quedó READY en {minutes} min")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("name"); ap.add_argument("model", nargs="?"); ap.add_argument("version", nargs="?", default="latest")
    ap.add_argument("--size", default="Small"); ap.add_argument("--status", action="store_true"); ap.add_argument("--wait", action="store_true")
    a = ap.parse_args()
    if a.status or not a.model:
        print(status(a.name)); sys.exit(0)
    upsert(a.name, a.model, a.version, a.size)
    if a.wait:
        wait(a.name)
