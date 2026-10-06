"""GET /insights (ADR-29): los hallazgos de datos (E10) en vivo, solo con agregados.
Corre el mismo SQL que va al warehouse, sobre data/mock cargado en SQLite."""
import csv
import importlib.util
import json
import os
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _load(tmp_path):
    os.environ["AGENT_MOCK_DIR"] = str(tmp_path / "mock")
    spec = importlib.util.spec_from_file_location("fh26_entry_insights", ROOT / "deploy" / "function" / "function_app.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _mock(name):
    return list(csv.DictReader(open(ROOT / "data" / "mock" / f"{name}.csv", encoding="utf-8")))


def test_umbral_sale_del_catalogo(tmp_path):
    mod = _load(tmp_path)
    cat = yaml.safe_load((ROOT / "policy" / "catalog.yaml").read_text(encoding="utf-8"))["products"]
    assert mod._threshold(ROOT) == Counter(p["min_score"] for p in cat).most_common(1)[0][0]


def test_clientes_de_prueba_fuera_y_totales_cuadran(tmp_path):
    mod = _load(tmp_path)
    b = mod.build_insights(mod._mock_executor(ROOT), mod._threshold(ROOT), "mock")
    reales = [r for r in _mock("customer_360") if not r["customer_id"].startswith("TEST-")]
    assert b["coverage"]["customers"] == len(reales)  # ADR-22: los TEST-* no cuentan
    assert sum(s["customers"] for s in b["segments"]) == len(reales)
    assert abs(sum(s["share_pct"] for s in b["segments"]) - 100) < 0.5
    assert sum(d["contacts"] for d in b["demand"]) == round(sum(float(r["volume"]) for r in _mock("contact_demand")))
    assert abs(sum(d["share_pct"] for d in b["demand"]) - 100) < 0.5
    assert [d["contacts"] for d in b["demand"]] == sorted((d["contacts"] for d in b["demand"]), reverse=True)


def test_umbral_por_segmento_coincide_con_un_conteo_a_mano(tmp_path):
    mod = _load(tmp_path)
    t = mod._threshold(ROOT)
    b = mod.build_insights(mod._mock_executor(ROOT), t, "mock")
    for s in b["segments"]:
        scores = [float(r["credit_score"]) for r in _mock("customer_360")
                  if r["segment"] == s["segment"] and not r["customer_id"].startswith("TEST-") and r["credit_score"]]
        assert s["below_threshold_pct"] == round(100 * sum(x < t for x in scores) / len(scores), 1)
        assert s["near_threshold_pct"] == round(100 * sum(t - 25 <= x <= t + 25 for x in scores) / len(scores), 1)


def test_solo_agregados_ningun_id_de_cliente(tmp_path):
    mod = _load(tmp_path)
    body = json.dumps(mod.build_insights(mod._mock_executor(ROOT), mod._threshold(ROOT), "mock"))
    ids = {r["customer_id"] for r in _mock("customer_360")}
    assert not any(i in body for i in ids)  # ADR-12
    assert "customer_id" not in body


def test_endpoint_publico_con_cache(tmp_path):
    mod = _load(tmp_path)
    import azure.functions as func
    req = func.HttpRequest(method="GET", url="/api/insights", body=b"")
    r = mod.insights.build().get_user_function()(req) if hasattr(mod.insights, "build") else mod.insights(req)
    assert r.status_code == 200 and "max-age=3600" in r.headers.get("Cache-Control", "")
    assert {"demand", "segments", "coverage", "threshold"} <= set(json.loads(r.get_body()))
