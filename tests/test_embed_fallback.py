"""search_policy sigue solo con léxico + enrutado cuando el endpoint de embeddings no responde (frío de scale-to-zero, 403, red)."""
from agent import tools as T


class _EmbedCaido:
    model_version = "serving:embed-bge-m3"

    def embed(self, texts):
        raise TimeoutError("read timed out")


def test_fallback_lexico_responde_con_citas(deps):
    d = deps.__class__(**{**deps.__dict__, "embed": _EmbedCaido()})
    r = T.search_policy(d, "¿Cuál es la tasa del préstamo personal?", "CO", "es")
    assert r["embed_fallback"] is True and r["embedding_model_version"] == "lexical-fallback"
    assert r["chunks"] and all(c["chunk_id"].startswith("POL-CO") for c in r["chunks"])


def test_sin_fallo_no_marca_fallback(deps):
    r = T.search_policy(deps, "¿Cuál es la tasa del préstamo personal?", "CO", "es")
    assert r["embed_fallback"] is False and r["embedding_model_version"] == deps.embed.model_version
