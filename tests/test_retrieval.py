"""Corpus y retrieval (iteración 1): esquema de chunks, cobertura R1–R8 y Recall@5 con BM25 como baseline."""
import json
import yaml
from eval.retrieval_eval import run


def _chunks(settings):
    return [json.loads(l) for l in open(settings.mock_dir / "policy_chunks.jsonl", encoding="utf-8")]


def test_chunks_cumplen_contrato(settings):
    spec = yaml.safe_load(open("contracts/chunks.yaml", encoding="utf-8"))["chunk"]
    required = set(spec) - {"embedding"}
    for c in _chunks(settings):
        assert required <= set(c), c["chunk_id"]
        assert c["es_sintetico"] is True and c["language"] in ("es", "pt") and c["country"] in ("CO", "MX", "AR")
        assert c["rule_id"] in {f"R{i}" for i in range(1, 9)} and c["chunk_id"] == f"{c['doc_id']}-{c['rule_id']}"


def test_corpus_cubre_3_paises_3_productos_2_idiomas_8_secciones(settings):
    ch = _chunks(settings)
    docs = {c["doc_id"] for c in ch}
    assert len(docs) == 18 and len(ch) == 144
    assert all(sum(1 for c in ch if c["doc_id"] == d) == 8 for d in docs)


def test_r3_r6_r7_citan_norma_con_url(settings):
    for c in _chunks(settings):
        if c["rule_id"] in ("R3", "R6", "R7"):
            assert c["url"].startswith("https://") and c["source"] != "catálogo sintético", c["chunk_id"]


def test_recall_at_5_hybrid_y_baseline_por_idioma():
    r = run(5)
    assert r["hybrid"]["es"] >= 0.8 and r["hybrid"]["pt"] >= 0.8, r   # lo que usa el agente
    assert r["bm25"]["es"] >= 0.8 and r["bm25"]["pt"] >= 0.8, r       # baseline ADR-06
    # el embedding mock (hash) solo se reporta; el umbral aplica al real (ADR-21 go/no-go int8 en PT)
    if not r["embedding_model"].startswith("mock"):
        assert r["embed"]["es"] >= 0.8 and r["embed"]["pt"] >= 0.8, r
