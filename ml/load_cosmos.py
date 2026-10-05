"""Carga policy_chunks a Cosmos con el vector real (ADR-21 §1: el mismo endpoint embed-bge-m3 para chunk y consulta).

    python ml/load_cosmos.py                 # embebe con el endpoint EMBED_ENDPOINT y hace upsert (288 docs, throttle 400 RU/s)
    python ml/load_cosmos.py --local         # embebe en local con bge-m3 (mismo modelo) si el endpoint aún no está READY
    python ml/load_cosmos.py --verify        # cuenta docs y corre una consulta vectorial y una de texto en es y pt

Requiere COSMOS_ENDPOINT / COSMOS_KEY en .env. Documento = contracts/chunks.yaml v2.1 + embedding. id = chunk_id, pk = country."""
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


def embedder(local: bool):
    if local:
        from sentence_transformers import SentenceTransformer
        m = SentenceTransformer("BAAI/bge-m3", device="cpu")
        return lambda texts: m.encode(texts, batch_size=16, normalize_embeddings=True, convert_to_numpy=True).tolist(), "local:bge-m3"
    from agent.adapters.embed_serving import EmbedServing
    from agent.config.settings import Settings
    e = EmbedServing(Settings())
    return e.embed, e.model_version


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--local", action="store_true"); ap.add_argument("--verify", action="store_true")
    a = ap.parse_args()
    from azure.cosmos import CosmosClient
    db = CosmosClient(os.environ["COSMOS_ENDPOINT"], os.environ["COSMOS_KEY"]).get_database_client(os.environ.get("COSMOS_DATABASE", "agent"))
    cont = db.get_container_client("policy_chunks")
    if a.verify:
        from agent.adapters.store_cosmos import StoreCosmos
        emb, ver = embedder(a.local)
        st = StoreCosmos(None)
        n = next(iter(cont.query_items("SELECT VALUE COUNT(1) FROM c", enable_cross_partition_query=True)))
        print(f"policy_chunks: {n} docs")
        for lang, q, cc in (("es", "¿Cuál es la tasa del préstamo personal?", "CO"), ("pt", "Quais os requisitos do cartão de crédito?", "CO")):
            v = emb([q])[0]
            print(lang, "vector:", [r["chunk_id"] for r in st.search(v, {"country": cc, "language": lang}, k=3)])
            print(lang, "texto: ", [r["chunk_id"] for r in st.search_text(q, {"country": cc, "language": lang}, k=3)])
        return
    rows = [json.loads(l) for l in open(ROOT / "data" / "mock" / "policy_chunks.jsonl", encoding="utf-8") if l.strip()]
    emb, ver = embedder(a.local)
    t0 = time.time(); done = 0
    for i in range(0, len(rows), 32):
        batch = rows[i:i + 32]
        vecs = emb([r["text"] for r in batch])
        for r, v in zip(batch, vecs):
            doc = {**r, "id": r["chunk_id"], "embedding": v, "embedding_model_version": ver}
            for _ in range(5):  # throttle 400 RU/s: reintento con espera si 429
                try:
                    cont.upsert_item(doc); break
                except Exception as e:  # noqa: BLE001
                    if "429" in str(e) or "TooManyRequests" in type(e).__name__:
                        time.sleep(1.0); continue
                    raise
            done += 1
        print(f"{done}/{len(rows)} · {int(time.time() - t0)}s", flush=True)
    print(f"cargados {done} chunks con {ver}")


if __name__ == "__main__":
    main()
