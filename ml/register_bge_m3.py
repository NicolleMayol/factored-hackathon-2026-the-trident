"""Registra bge-m3 en Unity Catalog como hackathon.ml.bge_m3 (ADR-21 §1) y mide el go/no-go int8 en PT.

    python ml/register_bge_m3.py --go-no-go          # Recall@5 en PT: fp32 vs int8 (local, sin registrar)
    python ml/register_bge_m3.py --register           # registra la variante elegida (int8 si pasó el go/no-go, si no fp32)
    python ml/serving.py embed-bge-m3 hackathon.ml.bge_m3 1 --size Small --wait

Modelo: BAAI/bge-m3 (1024 dims, multilingüe, es+pt), vía sentence-transformers. int8: cuantización dinámica de torch (Linear → int8),
sin ONNX, para que la misma clase sirva en Model Serving. Regla del go/no-go (ADR-21): Recall@5 PT int8 ≥ fp32 − 0,02 sobre los
casos PT de eval/retrieval_cases.jsonl; si no pasa, se registra fp32 y queda escrito. El pyfunc expone {"inputs": [textos]} →
lista de vectores normalizados, el mismo contrato que usan embed_serving.py (agente) y ml/load_cosmos.py (carga)."""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
try:
    from dotenv import load_dotenv; load_dotenv(ROOT / ".env")
except Exception:  # noqa: BLE001
    pass

MODEL_ID = "BAAI/bge-m3"
UC_NAME = "hackathon.ml.bge_m3"
EXPERIMENT = os.environ.get("MLFLOW_EXPERIMENT", "/Shared/fh26/agente")


def load(int8: bool):
    import torch
    from sentence_transformers import SentenceTransformer
    m = SentenceTransformer(MODEL_ID, device="cpu")
    if int8:
        import warnings
        warnings.filterwarnings("ignore")
        for engine in ([torch.backends.quantized.engine] if torch.backends.quantized.engine != "none" else []) + [e for e in ("qnnpack", "fbgemm", "x86") if e in torch.backends.quantized.supported_engines]:
            try:
                torch.backends.quantized.engine = engine
                m[0].auto_model = torch.quantization.quantize_dynamic(m[0].auto_model, {torch.nn.Linear}, dtype=torch.qint8)
                return m
            except Exception:  # noqa: BLE001 — probar el siguiente motor
                continue
        raise RuntimeError(f"int8 no disponible en este hardware (motores: {torch.backends.quantized.supported_engines})")
    return m


def embed(m, texts: list[str]) -> list[list[float]]:
    return m.encode(texts, batch_size=16, normalize_embeddings=True, convert_to_numpy=True).tolist()


def recall_at_5(m, lang: str) -> tuple[float, float]:
    """Recall@5 sobre eval/retrieval_cases.jsonl para un idioma, con el corpus de data/mock/policy_chunks.jsonl. Devuelve (recall, ms_por_consulta)."""
    chunks = [json.loads(l) for l in open(ROOT / "data" / "mock" / "policy_chunks.jsonl", encoding="utf-8")]
    cases = [json.loads(l) for l in open(ROOT / "eval" / "retrieval_cases.jsonl", encoding="utf-8")]
    cases = [c for c in cases if c.get("language") == lang]
    vecs = embed(m, [c["text"] for c in chunks])
    hits, t0 = 0, time.time()
    for c in cases:
        q = embed(m, [c["query"]])[0]
        pool = [(sum(a * b for a, b in zip(q, v)), ch) for ch, v in zip(chunks, vecs) if ch["language"] == lang and (not c.get("country") or ch["country"] == c["country"])]
        pool.sort(key=lambda t: -t[0])
        if any(ch["chunk_id"] == c["expected_chunk"] for _, ch in pool[:5]):
            hits += 1
    return round(hits / max(1, len(cases)), 3), round((time.time() - t0) * 1000 / max(1, len(cases)), 1)




def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--go-no-go", action="store_true"); ap.add_argument("--register", action="store_true"); ap.add_argument("--force-fp32", action="store_true")
    a = ap.parse_args()
    import mlflow
    import mlflow.pyfunc
    result_path = ROOT / "ml" / "results" / "bge_m3_go_no_go.json"
    choice = "fp32"
    if a.go_no_go or (a.register and not a.force_fp32 and not result_path.exists()):
        res = {}
        for variant in ("fp32", "int8"):
            try:
                m = load(int8=variant == "int8")
            except RuntimeError as e:
                res[variant] = {"error": str(e)}; print(variant, res[variant], flush=True); continue
            r_pt, ms_pt = recall_at_5(m, "pt"); r_es, ms_es = recall_at_5(m, "es")
            res[variant] = {"recall5_pt": r_pt, "recall5_es": r_es, "ms_query_pt": ms_pt, "ms_query_es": ms_es}
            print(variant, res[variant], flush=True)
        measurable = "recall5_pt" in res.get("int8", {})
        ok = measurable and res["int8"]["recall5_pt"] >= res["fp32"]["recall5_pt"] - 0.02
        choice = "int8" if ok else "fp32"
        res["decision"] = {"int8_go": ok, "registered_variant": choice, "rule": "Recall@5 PT int8 >= fp32 - 0.02 (ADR-21)",
                           "nota": None if measurable else "int8 no medible en el hardware local (sin motor de cuantización); se registra fp32 y el go/no-go int8 queda To-Be en CPU x86"}
        result_path.parent.mkdir(parents=True, exist_ok=True); result_path.write_text(json.dumps(res, indent=1), encoding="utf-8")
        print(json.dumps(res["decision"]))
    elif result_path.exists():
        choice = json.loads(result_path.read_text())["decision"]["registered_variant"]
    if a.force_fp32:
        choice = "fp32"
    if not a.register:
        return
    m = load(int8=choice == "int8")
    mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "databricks")); mlflow.set_experiment(EXPERIMENT); mlflow.set_registry_uri("databricks-uc")

    class _Embed(mlflow.pyfunc.PythonModel):
        def load_context(self, context):
            import torch
            from sentence_transformers import SentenceTransformer
            self.m = SentenceTransformer(context.artifacts["model"], device="cpu")
            if context.model_config and context.model_config.get("int8"):
                self.m[0].auto_model = torch.quantization.quantize_dynamic(self.m[0].auto_model, {torch.nn.Linear}, dtype=torch.qint8)

        def predict(self, context, model_input, params=None):
            texts = model_input["inputs"].tolist() if hasattr(model_input, "columns") and "inputs" in model_input.columns else list(model_input)
            return self.m.encode([str(t) for t in texts], batch_size=16, normalize_embeddings=True, convert_to_numpy=True).tolist()

    local = ROOT / "ml" / "artifacts" / "bge-m3"
    load(int8=False).save(str(local))  # se guarda fp32; int8 se aplica al cargar (la cuantización dinámica no se serializa)
    with mlflow.start_run(run_name=f"bge-m3-{choice}") as run:
        if result_path.exists():
            mlflow.log_dict(json.loads(result_path.read_text()), "go_no_go.json")
        mlflow.log_params({"model": MODEL_ID, "variant": choice, "dims": 1024})
        info = mlflow.pyfunc.log_model(name="model", python_model=_Embed(), artifacts={"model": str(local)}, model_config={"int8": choice == "int8"},
                                       input_example={"inputs": ["¿Cuál es la tasa del préstamo personal?"]}, pip_requirements=["sentence-transformers>=3.0", "torch", "numpy"],
                                       registered_model_name=UC_NAME)
        print(f"registrado {UC_NAME} ({choice}) · run {run.info.run_id} · {info.model_uri}")


if __name__ == "__main__":
    main()
