"""Embeddings reales: endpoint de Model Serving EMBED_ENDPOINT (hackathon.ml.bge_m3, ml/register_bge_m3.py). 1024 dims normalizados.
Mismo endpoint para la carga de chunks (ml/load_cosmos.py) y para la consulta en el nodo Act: un solo vector para chunk y consulta (ADR-21 §1).
Misma interfaz que EmbedMock. Lotes de 32; timeout de tool; el frío lo tolera run_tool."""
from __future__ import annotations
import requests
from agent.adapters import dbx_auth


class EmbedServing:
    model_version = "bge-m3"

    def __init__(self, settings):
        self.s = settings
        self.host = (settings.databricks_host or dbx_auth.host()).rstrip("/")
        self.endpoint = settings.embed_endpoint
        self.model_version = f"serving:{self.endpoint}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), 32):
            batch = texts[i:i + 32]
            r = requests.post(f"{self.host}/serving-endpoints/{self.endpoint}/invocations", timeout=(self.s.embed_query_timeout_s if len(texts) == 1 else max(self.s.tool_timeout_cold_s, 60)),  # 1 texto = consulta del agente: corto; lotes = carga
                              headers={**dbx_auth.auth_headers(), "Content-Type": "application/json"}, json={"inputs": batch})
            r.raise_for_status()
            pred = r.json().get("predictions", [])
            if len(pred) != len(batch):
                raise RuntimeError(f"embed_serving: {len(pred)} vectores para {len(batch)} textos")
            out.extend([list(map(float, v)) for v in pred])
        return out
