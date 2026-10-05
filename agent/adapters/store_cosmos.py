"""Store real: Azure Cosmos DB NoSQL (contracts/chunks.yaml, infra.yaml · cosmos). Misma interfaz que StoreLocal.

policy_chunks (pk /country): búsqueda vectorial con VectorDistance sobre /embedding (diskANN, coseno, 1024) y de texto completo con
FullTextScore sobre /text_es o /text_pt según el idioma; el RRF lo hace search_policy (agent/tools), igual que con el store local.
handoffs (pk /case_id): escritura idempotente por case_id. conversations lo gestiona servicio.
Credenciales: COSMOS_ENDPOINT + COSMOS_KEY (Key Vault en Azure; .env en local). Lectura con consistencia de sesión."""
from __future__ import annotations
import os
from typing import Any

FIELDS = "c.chunk_id, c.doc_id, c.text, c.language, c.country, c.product_code, c.rule_id, c.version, c.valid_from, c.valid_to, c.source, c.url"


class StoreCosmos:
    def __init__(self, settings, embed=None):
        from azure.cosmos import CosmosClient
        ep, key = os.environ.get("COSMOS_ENDPOINT", ""), os.environ.get("COSMOS_KEY", "")
        if not (ep and key):
            raise RuntimeError("store_cosmos: faltan COSMOS_ENDPOINT / COSMOS_KEY")
        db = CosmosClient(ep, key, consistency_level="Session").get_database_client(os.environ.get("COSMOS_DATABASE", "agent"))
        self.chunks = db.get_container_client("policy_chunks")
        self.handoffs = db.get_container_client("handoffs")

    @staticmethod
    def _where(filters: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
        conds, params = [], []
        for f in ("country", "language", "product_code"):
            if filters.get(f):
                conds.append(f"c.{f} = @{f}"); params.append({"name": f"@{f}", "value": filters[f]})
        return (" AND ".join(conds) or "true"), params

    def search(self, query_vec: list[float], filters: dict[str, Any], k: int = 5) -> list[dict[str, Any]]:
        where, params = self._where(filters)
        q = (f"SELECT TOP @k {FIELDS}, VectorDistance(c.embedding, @v) AS dist FROM c WHERE {where} "
             "ORDER BY VectorDistance(c.embedding, @v)")
        params += [{"name": "@k", "value": k}, {"name": "@v", "value": query_vec}]
        rows = list(self.chunks.query_items(q, parameters=params, partition_key=filters.get("country"), enable_cross_partition_query=not filters.get("country")))
        return [{**{kk: vv for kk, vv in r.items() if kk != "dist"}, "score": round(1 - float(r["dist"]), 4)} for r in rows]

    def search_text(self, query: str, filters: dict[str, Any], k: int = 5) -> list[dict[str, Any]]:
        lang = filters.get("language") or "es"
        path = "c.text_pt" if lang == "pt" else "c.text_es"
        terms = [t for t in _terms(query) if t][:8]
        if not terms:
            return []
        where, params = self._where(filters)
        q = (f"SELECT TOP @k {FIELDS} FROM c WHERE {where} AND IS_DEFINED({path}) "
             f"ORDER BY RANK FullTextScore({path}, {', '.join(f'@t{i}' for i in range(len(terms)))})")
        params += [{"name": "@k", "value": k}] + [{"name": f"@t{i}", "value": t} for i, t in enumerate(terms)]
        rows = list(self.chunks.query_items(q, parameters=params, partition_key=filters.get("country"), enable_cross_partition_query=not filters.get("country")))
        n = len(rows)
        return [{**r, "score": round((n - i) / max(n, 1), 4)} for i, r in enumerate(rows)]  # FullTextScore no devuelve el valor; el rango basta para RRF

    def put_handoff(self, doc: dict[str, Any]) -> None:
        self.handoffs.upsert_item({**doc, "id": doc["case_id"]})

    def get_handoff(self, case_id: str) -> dict[str, Any] | None:
        try:
            return self.handoffs.read_item(case_id, partition_key=case_id)
        except Exception:  # noqa: BLE001  — CosmosResourceNotFoundError
            return None


def _terms(text: str) -> list[str]:
    import re
    stop = set("de la el los las del en y a para por con un una que es o al lo mi me se su sus qué cuál cuánto cómo da do dos das em e um uma ou ao no na nos nas meu minha qual quanto como".split())
    return [w for w in re.findall(r"\w+", text.lower()) if w not in stop and len(w) > 2]
