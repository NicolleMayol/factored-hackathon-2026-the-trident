"""Locale del turno (fix del 5 oct): un locale corto en el body ya no rompe el escalamiento."""
import pytest
from agent.handle import pick_locale
from agent.handoff import _schema


@pytest.mark.parametrize("pedido,token,esperado", [
    ("es-AR", "es-CO", "es-AR"),   # válido: se respeta
    ("es", "es-CO", "es-CO"),      # corto en español: el del token
    ("pt", "es-CO", "pt-BR"),      # corto en portugués: pt-BR
    (None, "pt-BR", "pt-BR"),      # sin locale (la UI): el del token
    ("xx", None, "es-MX"),         # basura y token sin locale: el valor por defecto
])
def test_pick_locale(pedido, token, esperado):
    assert pick_locale(pedido, token) == esperado
    assert esperado in _schema()["properties"]["locale"]["enum"]
