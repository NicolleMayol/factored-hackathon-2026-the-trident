"""Modelo pyfunc de bge-m3 para Model Serving, en "models from code" (ADR-21 §1).

MLflow guarda ESTE archivo en vez de un pickle: la primera versión registrada arrastraba un `python_model.pkl` de 3,4 GB
(cloudpickle serializó por valor una clase definida dentro de main() con el modelo cargado), y el contenedor nunca pasaba la
prueba de salud. Contrato: {"inputs": [textos]} → lista de vectores normalizados (1024 dims); el mismo que usan
agent/adapters/embed_serving.py y ml/load_cosmos.py. int8 (cuantización dinámica) se aplica al cargar si model_config lo pide.
"""
from __future__ import annotations
import os

import mlflow
import mlflow.pyfunc


class BgeM3(mlflow.pyfunc.PythonModel):
    def load_context(self, context):
        os.environ.setdefault("HF_HUB_OFFLINE", "1"); os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")  # sin internet en Model Serving
        import torch
        from sentence_transformers import SentenceTransformer
        self.m = SentenceTransformer(context.artifacts["model"], device="cpu", local_files_only=True)
        if context.model_config and context.model_config.get("int8"):
            self.m[0].auto_model = torch.quantization.quantize_dynamic(self.m[0].auto_model, {torch.nn.Linear}, dtype=torch.qint8)

    def predict(self, context, model_input, params=None):
        texts = model_input["inputs"].tolist() if hasattr(model_input, "columns") and "inputs" in model_input.columns else list(model_input)
        return self.m.encode([str(t) for t in texts], batch_size=16, normalize_embeddings=True, convert_to_numpy=True).tolist()


mlflow.models.set_model(BgeM3())
