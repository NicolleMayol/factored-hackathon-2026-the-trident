"""Policy engine determinista (ADR-05). Evalúa policy/policy.yaml × scopes × flags → acción. Sin LLM.
Dos funciones: decide() para el nodo Decide y evaluate_eligibility() para la tool del mismo nombre (catálogo + reglas de negocio).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any
import yaml

ACTION_ORDER = ["reject", "block", "escalate", "clarify", "abstain", "confirm", "auto"]  # prioridad: lo más restrictivo gana
ACTION_TO_API = {"auto": "answer", "confirm": "confirm", "clarify": "clarify", "escalate": "escalate", "abstain": "answer", "block": "blocked", "reject": "reject"}
TOOLS_BY_INTENT = {
    "product_info": ["search_policy", "get_customer_products"],
    "eligibility_simulation": ["get_customer_profile", "get_customer_products", "search_policy", "get_prescore", "evaluate_eligibility"],
    "out_of_scope": [],
}


@dataclass
class Decision:
    action: str                      # auto|confirm|clarify|escalate|abstain|block|reject
    rules_fired: list[str]
    reason_code: str = ""
    allowed_tools: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def api_action(self) -> str:
        return ACTION_TO_API[self.action]


@lru_cache(maxsize=4)
def load_policy(path: str) -> dict[str, Any]:
    return yaml.safe_load(open(path, encoding="utf-8"))


def decide(ctx: dict[str, Any], policy_path: Path | str) -> Decision:
    """ctx: intent, intent_confidence, mixed_language, scopes, jwt_valid, user_consent, slots, required_slots,
    days_past_due, customer_status, fraud_flag, injection_detected, third_party_data_request, rules_outcome, prescore_ci_crosses_threshold."""
    pol = load_policy(str(policy_path))
    fired: list[dict[str, Any]] = []
    for rule in pol["rules"]:
        if _matches(rule, ctx):
            fired.append(rule)
    if not fired:
        d = pol["defaults"]
        return Decision(d["action"], [], d.get("reason_code", ""), [], ["default"])
    # la acción más restrictiva gana; P06 clarify solo una vez
    best = min(fired, key=lambda r: ACTION_ORDER.index(r["action"]))
    action = best["action"]
    if best["id"] == "P06" and ctx.get("clarifications", 0) >= best.get("max_clarifications", 1):
        action = best.get("then", "escalate")
    tools = TOOLS_BY_INTENT.get(ctx.get("intent", ""), []) if action in ("auto", "confirm") else []
    if "customer:read" not in ctx.get("scopes", []):
        tools = [t for t in tools if not t.startswith("get_customer")]
    if "credit:simulate" not in ctx.get("scopes", []):
        tools = [t for t in tools if t not in ("get_prescore", "evaluate_eligibility")]
    return Decision(action, [r["id"] for r in fired], best.get("reason_code", ""), tools)


def _matches(rule: dict[str, Any], ctx: dict[str, Any]) -> bool:
    if "intent" in rule:
        if ctx.get("intent") != rule["intent"]:
            return False
        for req in rule.get("requires", []):
            if req == "citation":
                continue  # lo exige Verify, no Decide
            if req == "jwt_valid" and not ctx.get("jwt_valid", True):
                return False
            if req.startswith("scope:") and req[6:] not in ctx.get("scopes", []):
                # sin scope: la regla no aplica; cae en default o en otra regla → escalate por scope
                ctx.setdefault("_scope_missing", []).append(req[6:])
                return False
            if req == "user_consent":
                continue  # se pide en /chat/confirm
        return True
    cond = rule.get("condition", "")
    return _eval_condition(cond, ctx)


def _eval_condition(cond: str, ctx: dict[str, Any]) -> bool:
    """Evalúa las condiciones del YAML sin eval(): cada átomo se mapea a una comprobación explícita."""
    c = cond.replace("'", "")
    checks = {
        "rules_outcome == Revisión humana": ctx.get("rules_outcome") == "Revisión humana",
        "prescore_ci_crosses_threshold": bool(ctx.get("prescore_ci_crosses_threshold")),
        "missing_required_slots": bool(ctx.get("missing_required_slots")),
        "days_past_due > 0": (ctx.get("days_past_due") or 0) > 0,
        "customer_status in [Suspended]": ctx.get("customer_status") == "Suspended",
        "fraud_flag": bool(ctx.get("fraud_flag")),
        "intent_confidence < 0.6": (ctx.get("intent_confidence") if ctx.get("intent_confidence") is not None else 1.0) < 0.6,
        "mixed_language": bool(ctx.get("mixed_language")),
        "injection_detected": bool(ctx.get("injection_detected")),
        "third_party_data_request": bool(ctx.get("third_party_data_request")),
        "jwt_invalid": bool(ctx.get("jwt_invalid")),
        "expired": bool(ctx.get("jwt_expired")),
    }
    atoms = [a.strip() for a in c.split(" or ")]
    for a in atoms:
        if a not in checks:
            raise ValueError(f"condición sin mapeo en el motor: {a!r}")
    return any(checks[a] for a in atoms)


# ---------- elegibilidad (tool evaluate_eligibility) ----------

# rate_kind que actúa como tope o referencia regulatoria por país (ref.regulator_rates, ADR-22 hallazgo rate_kind): CO usura (SFC), MX CAT (CONDUSEF), AR CFT (BCRA)
CAP_KIND = {"CO": "usura", "MX": "cat", "AR": "cft"}


def regulatory_cap(regulator_rates, country: str, product_type: str) -> float | None:
    kind = CAP_KIND.get(country, "usura")
    caps = [float(r["rate_max"]) for r in regulator_rates or [] if r.get("country") == country and r.get("product_type") == product_type and r.get("rate_kind", "usura") in (kind, "cap")]
    return caps[-1] if caps else None


@lru_cache(maxsize=4)
def load_catalog(path: str) -> list[dict[str, Any]]:
    data = yaml.safe_load(open(path, encoding="utf-8"))
    return data["products"] if isinstance(data, dict) else data


def evaluate_eligibility(profile: dict[str, Any], behavior: dict[str, Any], product_type: str, amount: float | None,
                         prescore: dict[str, Any] | None, country: str, catalog_path: Path | str,
                         regulator_rates: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Resultado determinista: Elegible | No elegible | Revisión humana, con reglas disparadas y explicación es/pt."""
    rules: list[str] = []
    cat = [p for p in load_catalog(str(catalog_path)) if p["country"] == country and p["product_type"] == product_type]
    if not cat:
        return {"outcome": "Revisión humana", "rules_fired": ["E00"], "explanation_es": "No hay un producto de este tipo en el catálogo de tu país.",
                "explanation_pt": "Não há um produto desse tipo no catálogo do seu país.", "product": None}
    p = cat[0]
    score = profile.get("credit_score")
    dpd = behavior.get("max_days_past_due") or 0
    status = profile.get("customer_status")
    income = profile.get("estimated_monthly_income") or 0
    outcome = "Elegible"
    if status == "Suspended":
        rules.append("E01"); outcome = "No elegible"
    if dpd > 30:
        rules.append("E02"); outcome = "No elegible"
    elif dpd > 0:
        rules.append("E03"); outcome = "Revisión humana" if outcome == "Elegible" else outcome
    if score is None:
        rules.append("E04"); outcome = "Revisión humana" if outcome == "Elegible" else outcome
    elif score < p.get("min_score", 600):
        rules.append("E05"); outcome = "No elegible"
    if amount is not None:
        if amount > float(p["amount_max"]):
            rules.append("E06"); outcome = "No elegible" if outcome != "Revisión humana" else outcome
        elif amount < float(p["amount_min"]):
            rules.append("E07"); outcome = "Revisión humana" if outcome == "Elegible" else outcome
        if income and amount > 0 and (amount / 12) > 0.4 * float(income):
            rules.append("E08"); outcome = "Revisión humana" if outcome == "Elegible" else outcome
    if prescore:
        lo, hi = prescore.get("ci_low", 0), prescore.get("ci_high", 1)
        if lo < 0.5 <= hi:
            rules.append("E09"); outcome = "Revisión humana" if outcome == "Elegible" else outcome
        elif hi < 0.5 and outcome == "Elegible":
            rules.append("E10"); outcome = "Revisión humana"
    # techo regulatorio: la tasa del catálogo nunca supera el tope del país (Verify también lo revisa)
    cap = regulatory_cap(regulator_rates, country, product_type)
    if cap is not None and float(p["rate_max"]) > cap:
        rules.append("E11"); outcome = "Revisión humana"
    texts = {
        "E01": ("tu cuenta está suspendida", "sua conta está suspensa"),
        "E02": ("tienes más de 30 días de mora", "você tem mais de 30 dias de atraso"),
        "E03": ("tienes mora reciente", "você tem atraso recente"),
        "E04": ("no tenemos tu puntaje de crédito", "não temos sua pontuação de crédito"),
        "E05": ("tu puntaje está por debajo del mínimo del producto", "sua pontuação está abaixo do mínimo do produto"),
        "E06": ("el monto supera el máximo del producto", "o valor supera o máximo do produto"),
        "E07": ("el monto está por debajo del mínimo", "o valor está abaixo do mínimo"),
        "E08": ("la cuota estimada supera el 40 % de tu ingreso", "a parcela estimada supera 40 % da sua renda"),
        "E09": ("tu perfil está en el límite y lo revisa una persona", "seu perfil está no limite e será revisado por uma pessoa"),
        "E10": ("tu perfil requiere revisión de una persona", "seu perfil requer revisão por uma pessoa"),
        "E11": ("la tasa del producto debe revisarse frente al tope regulatorio", "a taxa do produto deve ser revista frente ao teto regulatório"),
    }
    es = "; ".join(texts[r][0] for r in rules) or "cumples las condiciones preliminares"
    pt = "; ".join(texts[r][1] for r in rules) or "você cumpre as condições preliminares"
    return {"outcome": outcome, "rules_fired": rules, "explanation_es": es, "explanation_pt": pt,
            "product": {k: p[k] for k in ("product_code", "name_es", "name_pt", "rate_min", "rate_max", "amount_min", "amount_max", "term_months_max")}}
