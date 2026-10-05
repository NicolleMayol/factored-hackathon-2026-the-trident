import agent.adapters.embed_serving as es
from agent.config.settings import Settings


def test_embed_serving_lotes_y_forma(monkeypatch):
    monkeypatch.setenv("DATABRICKS_HOST", "https://x"); calls = []
    class R:
        status_code = 200
        def __init__(self, n): self.n = n
        def raise_for_status(self): pass
        def json(self): return {"predictions": [[0.1] * 1024 for _ in range(self.n)]}
    def fake_post(url, **kw):
        calls.append(len(kw["json"]["inputs"])); return R(len(kw["json"]["inputs"]))
    monkeypatch.setattr(es.requests, "post", fake_post); monkeypatch.setattr(es.dbx_auth, "auth_headers", lambda: {})
    v = es.EmbedServing(Settings()).embed([f"t{i}" for i in range(70)])
    assert calls == [32, 32, 6] and len(v) == 70 and len(v[0]) == 1024
