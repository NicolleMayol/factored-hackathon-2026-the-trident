"""Vector store y handoffs en local: policy_chunks.jsonl de data/mock + coseno en memoria; handoffs en un dict. Misma interfaz que store_cosmos."""
from __future__ import annotations
import json
import math
import re
from collections import Counter
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

    def search_text(self, query: str, filters: dict[str, Any], k: int = 5) -> list[dict[str, Any]]:
        """BM25 sobre los chunks filtrados; en Cosmos esto es la búsqueda de texto completo (hybrid search)."""
        rows = [r for r in self._load() if not any(filters.get(f) and r.get(f) != filters[f] for f in ("country", "language", "product_code"))]
        docs = [_tok(r["text"]) for r in rows]
        if not docs:
            return []
        avg = sum(map(len, docs)) / len(docs); df: Counter = Counter()
        for d in docs:
            df.update(set(d))
        q = _tok(query); out = []
        for r, d in zip(rows, docs):
            tf = Counter(d); s = 0.0
            for w in q:
                if w in tf:
                    idf = math.log(1 + (len(docs) - df[w] + 0.5) / (df[w] + 0.5))
                    s += idf * tf[w] * 2.5 / (tf[w] + 1.5 * (0.25 + 0.75 * len(d) / avg))
            if s > 0:
                out.append({**{kk: vv for kk, vv in r.items() if kk != "embedding"}, "score": round(s, 4)})
        out.sort(key=lambda x: -x["score"])
        return out[:k]

    def put_handoff(self, doc: dict[str, Any]) -> None:
        self._handoffs[doc["case_id"]] = doc

    def get_handoff(self, case_id: str) -> dict[str, Any] | None:
        return self._handoffs.get(case_id)


_STOP = set("de la el los las del en y a para por con un una que es o al lo mi me se su sus qué cuál cuánto cómo o do da dos das em e um uma que é ou ao no na nos nas o meu minha qual quanto como".split())


def _tok(t: str) -> list[str]:
    out = []
    for w in re.findall(r"\w+", t.lower()):
        if w in _STOP or len(w) < 2:
            continue
        if len(w) > 4 and w.endswith("es"):
            w = w[:-2]
        elif len(w) > 3 and w.endswith("s"):
            w = w[:-1]
        out.append(w)
    return out
