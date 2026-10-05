"""GET /meta (ADR-25): la UI se arma con los mismos archivos que lee el agente."""
import importlib.util
import json
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _load(tmp_path):
    os.environ["AGENT_MOCK_DIR"] = str(tmp_path / "mock")
    spec = importlib.util.spec_from_file_location("fh26_entry", ROOT / "deploy" / "function" / "function_app.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_meta_sale_de_las_fuentes(tmp_path):
    mod = _load(tmp_path)
    m = mod.build_meta(ROOT)
    catalog = yaml.safe_load((ROOT / "policy" / "catalog.yaml").read_text(encoding="utf-8"))
    assert set(m["products"]) == {p["product_code"] for p in catalog["products"]}
    assert set(m["countries"]) == {p["country"] for p in catalog["products"]}
    assert {u["key"] for u in m["users"]} == set(mod.SESSION_USERS)
    enum = json.loads((ROOT / "contracts" / "handoff.schema.json").read_text())["properties"]["reason_code"]["enum"]
    assert m["reason_codes"] == enum
    assert m["outcomes"] == ["Elegible", "No elegible", "Revisión humana"]


def test_meta_sin_datos_de_clientes(tmp_path):
    m = _load(tmp_path).build_meta(ROOT)
    assert "customer_id" not in json.dumps(m)
    assert {u["country"] for u in m["users"] if u["key"].startswith("cliente_")} <= set(m["countries"])


def test_ui_json_cubre_lo_que_expone_meta(tmp_path):
    """Cada código que /meta puede devolver tiene texto en web/ui.json para cada idioma."""
    m = _load(tmp_path).build_meta(ROOT)
    ui = json.loads((ROOT / "web" / "ui.json").read_text(encoding="utf-8"))
    for lang, t in ui["lang"].items():
        assert set(m["reason_codes"]) <= set(t["reasons"]), lang
        assert set(m["outcomes"]) <= set(t["outcomes"]), lang
        assert set(m["tools"]) <= set(t["tools"]), lang
        assert set(ui["lang"]["es"]) == set(t), f"{lang}: faltan o sobran claves frente a es"
