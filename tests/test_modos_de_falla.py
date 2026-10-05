"""ADR-28 · F08: si una dependencia falla o tarda (frío, 403, 500), el agente escala con case_id; nunca deja salir una excepción (500)."""
import dataclasses
import time

import pytest

from agent.adapters import build_deps
from agent.handle import confirm, handle, runtime


class Falla:
    """Envuelve un adaptador: cada método público levanta `exc` o tarda `delay` segundos."""
    def __init__(self, inner, exc=None, delay=0.0):
        self._inner, self._exc, self._delay = inner, exc, delay

    def __getattr__(self, name):
        attr = getattr(self._inner, name)
        if not callable(attr) or name.startswith("_"):
            return attr
        def wrapped(*a, **kw):
            if self._delay:
                time.sleep(self._delay)
            if self._exc:
                raise self._exc
            return attr(*a, **kw)
        return wrapped


def rt_con(settings, **fallas):
    s = dataclasses.replace(settings, tool_timeout_s=0.2, tool_timeout_cold_s=0.3, tool_retries=0)
    d = build_deps(s)
    for dep, falla in fallas.items():
        setattr(d, dep, Falla(getattr(d, dep), **falla))
    return runtime(s, d)


INFO = "¿Qué requisitos tiene el préstamo personal?"
SIM = "¿Califico para un préstamo personal de 5000000?"
ERRORES = [RuntimeError("SQL statement FAILED"), PermissionError("403 PERMISSION_DENIED"), ConnectionError("reset by peer")]


@pytest.mark.parametrize("exc", ERRORES, ids=lambda e: type(e).__name__)
@pytest.mark.parametrize("dep", ["store", "embed"])
def test_busqueda_que_falla_escala(settings, users, dep, exc):
    r = handle(INFO, users["cliente_co_ok"], rt=rt_con(settings, **{dep: {"exc": exc}}))
    # Los handoffs viven en el store: si el que falla es el store, se escala sin case_id pero con respuesta.
    assert r["action"] == "escalate" and r.get("reply") and (r.get("case_id") or dep == "store")


@pytest.mark.parametrize("exc", ERRORES, ids=lambda e: type(e).__name__)
@pytest.mark.parametrize("dep", ["sql", "prescore"])
def test_preevaluacion_con_dependencia_caida_escala(settings, users, dep, exc):
    rt = rt_con(settings, **{dep: {"exc": exc}})
    r = handle(SIM, users["cliente_co_ok"], rt=rt)
    if r["action"] == "confirm":  # la falla aparece al ejecutar la pre-evaluación ya autorizada
        r = confirm(r["action_id"], True, {"customer_id": users["cliente_co_ok"]["customer_id"]}, rt=rt)
    assert r["action"] == "escalate" and r.get("case_id")


@pytest.mark.parametrize("dep", ["sql", "store"])
def test_dependencia_lenta_escala_por_timeout(settings, users, dep):
    rt = rt_con(settings, **{dep: {"delay": 0.5}})
    r = handle(SIM if dep == "sql" else INFO, users["cliente_co_ok"], rt=rt)
    if r["action"] == "confirm":
        r = confirm(r["action_id"], True, {"customer_id": users["cliente_co_ok"]["customer_id"]}, rt=rt)
    assert r["action"] == "escalate" and r.get("reply") and (r.get("case_id") or dep == "store")


def test_llm_caido_no_tumba_el_turno(settings, users):
    r = handle(INFO, users["cliente_co_ok"], rt=rt_con(settings, llm={"exc": RuntimeError("FM API 403")}))
    assert r["action"] in {"answer", "clarify", "escalate"} and r.get("reply")
