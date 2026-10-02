"""Recall@K del retrieval por idioma, con BM25 como baseline (ADR-06).

    python eval/retrieval_eval.py            # embedding según AGENT_EMBED (mock en local) vs BM25
    python eval/retrieval_eval.py --k 5 --min 0.8

Casos: eval/retrieval_cases.jsonl (query, country, language, expected_chunk). Un caso acierta si el chunk esperado
está en el top-K con los filtros de país e idioma que usa la tool search_policy. Sale con código 1 si BM25 o el
embedding real quedan bajo --min; el embedding mock (hash) se reporta pero no bloquea.
"""
from __future__ import annotations
import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.adapters import build_deps  # noqa: E402
from agent.config.settings import get_settings  # noqa: E402
from agent.tools import search_policy  # noqa: E402

STOP = set("de la el los las del en y a para por con un una que es o al lo mi me se su sus qué cuál cuánto cómo o do da dos das em e um uma que é ou ao no na nos nas o meu minha qual quanto como".split())


def tok(t: str) -> list[str]:
    """tokens sin stopwords, con stem mínimo (plurales es/pt) para que reclamo ≈ reclamos."""
    out = []
    for w in re.findall(r"\w+", t.lower()):
        if w in STOP or len(w) < 2:
            continue
        if len(w) > 4 and w.endswith("es"):
            w = w[:-2]
        elif len(w) > 3 and w.endswith("s"):
            w = w[:-1]
        out.append(w)
    return out


class BM25:
    def __init__(self, docs: list[list[str]], k1=1.5, b=0.75):
        self.k1, self.b, self.docs = k1, b, docs
        self.avg = sum(map(len, docs)) / max(1, len(docs))
        self.df: Counter = Counter()
        for d in docs:
            self.df.update(set(d))
        self.n = len(docs)

    def score(self, q: list[str], i: int) -> float:
        d = self.docs[i]; tf = Counter(d); s = 0.0
        for w in q:
            if w not in tf:
                continue
            idf = math.log(1 + (self.n - self.df[w] + 0.5) / (self.df[w] + 0.5))
            s += idf * tf[w] * (self.k1 + 1) / (tf[w] + self.k1 * (1 - self.b + self.b * len(d) / self.avg))
        return s


def run(k: int) -> dict:
    s = get_settings(); d = build_deps(s)
    chunks = [json.loads(l) for l in open(s.mock_dir / "policy_chunks.jsonl", encoding="utf-8")]
    cases = [json.loads(l) for l in open(ROOT / "eval" / "retrieval_cases.jsonl", encoding="utf-8")]
    bm = BM25([tok(c["text"]) for c in chunks])
    hits = {"embed": defaultdict(list), "bm25": defaultdict(list), "hybrid": defaultdict(list)}
    misses = []
    for c in cases:
        flt = {"country": c["country"], "language": c["language"]}
        idx = [i for i, ch in enumerate(chunks) if ch["country"] == flt["country"] and ch["language"] == flt["language"]]
        # embedding (misma ruta que la tool search_policy)
        vec = d.embed.embed([c["query"]])[0]
        top_e = [h["chunk_id"] for h in d.store.search(vec, flt, k=k)]
        # bm25 baseline con los mismos filtros
        q = tok(c["query"])
        top_b = [chunks[i]["chunk_id"] for i in sorted(idx, key=lambda i: -bm.score(q, i))[:k]]
        top_h = [h["chunk_id"] for h in search_policy(d, c["query"], c["country"], c["language"])["chunks"]]
        for name, top in (("embed", top_e), ("bm25", top_b), ("hybrid", top_h)):
            ok = c["expected_chunk"] in top
            hits[name][c["language"]].append(ok)
            if not ok:
                misses.append((name, c["case_id"], c["language"], c["expected_chunk"], top[:3]))
    rep = {name: {lang: round(sum(v) / len(v), 3) for lang, v in by.items()} for name, by in hits.items()}
    for name in rep:
        allv = [x for v in hits[name].values() for x in v]
        rep[name]["all"] = round(sum(allv) / len(allv), 3)
    rep["embedding_model"] = d.embed.model_version
    rep["k"] = k
    rep["misses"] = misses
    return rep


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--k", type=int, default=5); ap.add_argument("--min", type=float, default=0.8)
    a = ap.parse_args()
    r = run(a.k)
    print(f"Recall@{a.k} · embedding={r['embedding_model']}")
    print(f"  embed : es={r['embed'].get('es')}  pt={r['embed'].get('pt')}  all={r['embed']['all']}")
    print(f"  bm25  : es={r['bm25'].get('es')}  pt={r['bm25'].get('pt')}  all={r['bm25']['all']}")
    print(f"  hybrid: es={r['hybrid'].get('es')}  pt={r['hybrid'].get('pt')}  all={r['hybrid']['all']}   (la tool search_policy: RRF + enrutado por sección)")
    for m in r["misses"]:
        print(f"  miss {m[0]} {m[1]} ({m[2]}): esperado {m[3]} · top3 {m[4]}")
    bad = r["hybrid"]["all"] < a.min or (not r["embedding_model"].startswith("mock") and r["embed"]["all"] < a.min)
    sys.exit(1 if bad else 0)
