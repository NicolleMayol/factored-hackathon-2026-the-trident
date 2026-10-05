"""ADR-28 F05: valores límite del motor de elegibilidad. Cada prueba mueve un solo parámetro sobre un perfil que pasa todo.
Los bordes salen del catálogo, no de números escritos a mano: si el catálogo cambia, las pruebas siguen apuntando al borde."""
import pytest
from agent.policy import engine

CAT = "data/mock/catalog.yaml"
PAIS, TIPO = "CO", "personal_loan"
PROD = next(p for p in engine.load_catalog(CAT) if p["country"] == PAIS and p["product_type"] == TIPO)
LEJOS = {"ci_low": 0.7, "ci_high": 0.9}  # pre-score lejos del umbral


def evaluar(score=None, dpd=0, status="Active", income=10**12, amount=None, prescore=LEJOS):
    perfil = {"credit_score": PROD["min_score"] + 100 if score is None else score, "customer_status": status, "estimated_monthly_income": income}
    return engine.evaluate_eligibility(perfil, {"max_days_past_due": dpd}, TIPO, amount, prescore, PAIS, CAT, [])


def test_perfil_base_es_elegible():
    r = evaluar(amount=PROD["amount_min"])
    assert r["outcome"] == "Elegible" and r["rules_fired"] == []


@pytest.mark.parametrize("delta,regla", [(-1, "E05"), (0, None), (1, None)])
def test_puntaje_en_el_minimo(delta, regla):
    r = evaluar(score=PROD["min_score"] + delta)
    assert (regla in r["rules_fired"]) if regla else ("E05" not in r["rules_fired"])
    assert r["outcome"] == ("No elegible" if regla else "Elegible")


@pytest.mark.parametrize("dpd,regla,outcome", [(0, None, "Elegible"), (1, "E03", "Revisión humana"), (30, "E03", "Revisión humana"), (31, "E02", "No elegible")])
def test_dias_de_mora(dpd, regla, outcome):
    r = evaluar(dpd=dpd)
    assert r["outcome"] == outcome
    assert r["rules_fired"] == ([regla] if regla else [])


@pytest.mark.parametrize("monto,regla,outcome", [
    (PROD["amount_max"], None, "Elegible"),
    (PROD["amount_max"] + 1, "E06", "No elegible"),
    (PROD["amount_min"], None, "Elegible"),
    (PROD["amount_min"] - 1, "E07", "Revisión humana"),
])
def test_monto_en_los_bordes_del_producto(monto, regla, outcome):
    r = evaluar(amount=monto)
    assert r["outcome"] == outcome
    assert r["rules_fired"] == ([regla] if regla else [])


@pytest.mark.parametrize("proporcion,dispara", [(0.40, False), (0.401, True)])
def test_cuota_frente_al_40_por_ciento_del_ingreso(proporcion, dispara):
    monto = PROD["amount_min"]
    ingreso = engine.monthly_payment(monto, PROD) / proporcion  # cuota = proporcion × ingreso
    r = evaluar(amount=monto, income=ingreso)
    assert ("E08" in r["rules_fired"]) is dispara
    assert r["outcome"] == ("Revisión humana" if dispara else "Elegible")


@pytest.mark.parametrize("lo,hi,regla", [
    (0.5, 0.9, None),    # IC empieza justo en el umbral: no lo cruza
    (0.49, 0.5, "E09"),  # IC termina justo en el umbral: lo cruza
    (0.4, 0.6, "E09"),
    (0.3, 0.49, "E10"),  # IC entero bajo el umbral
])
def test_intervalo_del_prescore_frente_al_umbral(lo, hi, regla):
    r = evaluar(prescore={"ci_low": lo, "ci_high": hi})
    assert r["rules_fired"] == ([regla] if regla else [])
    assert r["outcome"] == ("Revisión humana" if regla else "Elegible")


def test_cuenta_suspendida_no_es_elegible():
    r = evaluar(status="Suspended")
    assert r["outcome"] == "No elegible" and r["rules_fired"] == ["E01"]


@pytest.mark.parametrize("ingreso", [None, 0])
def test_ingreso_ausente_con_monto_va_a_humano(ingreso):
    r = evaluar(amount=PROD["amount_min"], income=ingreso)
    assert r["outcome"] == "Revisión humana" and r["rules_fired"] == ["E12"]


def test_lo_mas_restrictivo_gana_mora_grave_y_borde_del_prescore():
    r = evaluar(dpd=31, prescore={"ci_low": 0.4, "ci_high": 0.6})
    assert r["outcome"] == "No elegible" and r["rules_fired"] == ["E02", "E09"]
