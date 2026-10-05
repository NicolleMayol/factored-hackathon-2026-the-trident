"""store_cosmos sin Cosmos: se comprueba la forma de las consultas (parámetros, filtros, ORDER BY) y el mapeo de resultados."""
import sys, types
import agent.adapters.store_cosmos as sc


class FakeContainer:
    def __init__(self): self.calls = []; self.items = {}
    def query_items(self, q, parameters=None, partition_key=None, enable_cross_partition_query=False):
        self.calls.append((q, parameters, partition_key))
        if "VectorDistance" in q:
            return [{"chunk_id": "A", "text": "t", "dist": 0.1}, {"chunk_id": "B", "text": "u", "dist": 0.3}]
        return [{"chunk_id": "C", "text": "v"}, {"chunk_id": "D", "text": "w"}]
    def upsert_item(self, d): self.items[d["id"]] = d
    def read_item(self, i, partition_key=None):
        if i not in self.items: raise KeyError(i)
        return self.items[i]


def _store(monkeypatch):
    monkeypatch.setenv("COSMOS_ENDPOINT", "https://c"); monkeypatch.setenv("COSMOS_KEY", "k")
    fake = types.ModuleType("azure.cosmos"); chunks, hand = FakeContainer(), FakeContainer()
    class DB:
        def get_container_client(self, n): return chunks if n == "policy_chunks" else hand
    class Client:
        def __init__(self, *a, **k): pass
        def get_database_client(self, n): return DB()
    fake.CosmosClient = Client; sys.modules["azure.cosmos"] = fake; sys.modules.setdefault("azure", types.ModuleType("azure"))
    return sc.StoreCosmos(None), chunks, hand


def test_vector_query_con_filtros(monkeypatch):
    st, chunks, _ = _store(monkeypatch)
    out = st.search([0.0] * 1024, {"country": "CO", "language": "es", "product_code": "CO-PL-01"}, k=5)
    q, params, pk = chunks.calls[0]
    assert "VectorDistance(c.embedding, @v)" in q and "c.country = @country" in q and "c.product_code = @product_code" in q and pk == "CO"
    assert {p["name"] for p in params} == {"@country", "@language", "@product_code", "@k", "@v"} and out[0]["chunk_id"] == "A" and out[0]["score"] == 0.9


def test_fulltext_por_idioma(monkeypatch):
    st, chunks, _ = _store(monkeypatch)
    out = st.search_text("Quais os requisitos do cartão de crédito?", {"country": "CO", "language": "pt"}, k=5)
    q, params, _ = chunks.calls[0]
    assert "FullTextScore(c.text_pt" in q and "IS_DEFINED(c.text_pt)" in q and any(p["value"] == "requisitos" for p in params)
    assert [r["chunk_id"] for r in out] == ["C", "D"] and out[0]["score"] > out[1]["score"]


def test_handoff_idempotente(monkeypatch):
    st, _, hand = _store(monkeypatch)
    st.put_handoff({"case_id": "H1", "x": 1}); st.put_handoff({"case_id": "H1", "x": 2})
    assert st.get_handoff("H1")["x"] == 2 and st.get_handoff("nope") is None and len(hand.items) == 1
