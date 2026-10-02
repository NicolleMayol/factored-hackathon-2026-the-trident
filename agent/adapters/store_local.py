"""Vector store y handoffs en local: policy_chunks.jsonl de data/mock + coseno en memoria; handoffs en un dict. Misma interfaz que store_cosmos."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any


class StoreLocal:
    def __init__(self, settings, embed):
        self.path = Path(settings.mock_dir) / "policy_chunks.jsonl"
        self.embed = embed
        self._chunks: list[dict[str, Any]] | None = None
        self._handoffs: dict[str, dict[str, Any]] = {}

    def _load(self) -> list[dict[str, Any]]:
        if self._chunks is None:
            rows = [json.loads(l) for l in open(self.path, encoding="utf-8") if l.strip()]
            vecs = self.embed.embed([r["text"] for r in rows])
            for r, v in zip(rows, vecs):
                r["embedding"] = v
            self._chunks = rows
        return self._chunks

    def search(self, query_vec: list[float], filters: dict[str, Any], k: int = 5) -> list[dict[str, Any]]:
        out = []
        for r in self._load():
            if any(filters.get(f) and r.get(f) != filters[f] for f in ("country", "language", "product_code")):
                continue
            if r.get("valid_to"):
                pass  # vigencia: filtro simple; en Cosmos va en la query
            score = sum(a * b for a, b in zip(query_vec, r["embedding"]))
            out.append({**{kk: vv for kk, vv in r.items() if kk != "embedding"}, "score": round(score, 4)})
        out.sort(key=lambda x: -x["score"])
        return out[:k]

    def put_handoff(self, doc: dict[str, Any]) -> None:
        self._handoffs[doc["case_id"]] = doc

    def get_handoff(self, case_id: str) -> dict[str, Any] | None:
        return self._handoffs.get(case_id)
