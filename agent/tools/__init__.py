"""Tools tipadas según contracts/tools.yaml. customer_id SIEMPRE sale del JWT. Cada tool devuelve dict serializable y lleva timeout/retries en el ejecutor."""
from __future__ import annotations
import concurrent.futures as cf
import re
import time
from typing import Any, Callable

from agent.adapters import Deps
from agent.policy.engine import evaluate_eligibility

TOOL_SCOPES = {"get_customer_profile": "customer:read", "get_customer_products": "customer:read", "search_policy": "public",
               "get_prescore": "credit:simulate", "evaluate_eligibility": "credit:simulate", "create_handoff": "always"}
TOOL_DEP = {"get_customer_profile": "sql", "get_customer_products": "sql", "search_policy": "embed", "get_prescore": "prescore",
            "evaluate_eligibility": "sql", "create_handoff": "cosmos"}


class ToolTimeout(Exception):
    pass


def run_tool(name: str, fn: Callable[[], Any], deps: Deps, settings, *, cold_used: set[str]) -> Any:
    """Ejecuta con timeout 8 s (25 s una sola vez por dependencia y conversación si /healthz dice cold), 2 retries."""
    dep = TOOL_DEP[name]
    timeout = settings.tool_timeout_s
    if deps.health.get(dep) == "cold" and dep not in cold_used:
        timeout = settings.tool_timeout_cold_s
        cold_used.add(dep)
    last: Exception | None = None
    for attempt in range(settings.tool_retries + 1):
        with cf.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(fn)
            try:
                return fut.result(timeout=timeout)
            except cf.TimeoutError:
                last = ToolTimeout(f"{name}: timeout {timeout}s")
            except Exception as e:  # noqa: BLE001
                last = e
        time.sleep(0.05 * attempt)
    raise last  # type: ignore[misc]


COUNTRY_ISO = {"Mexico": "MX", "México": "MX", "Colombia": "CO", "Argentina": "AR"}  # fallback si gold.customer_360 aún no trae country_code (ADR-22/#27)


def get_customer_profile(deps: Deps, customer_id: str) -> dict[str, Any]:
    rows = deps.sql.query("customer_profile", {"customer_id": customer_id})
    if not rows:
        return {"found": False}
    r = rows[0]
    # nunca se devuelven columnas excluidas ni documento
    out = {"found": True, **{k: r.get(k) for k in ("customer_id", "country", "segment", "credit_score", "estimated_monthly_income", "customer_status", "detected_accent")}}
    # dos convenciones de país en gold (nombre en customer_360, ISO-2 en catálogo/tasas/chunks): la tool entrega la llave ISO-2 en un solo sitio
    out["country_code"] = r.get("country_code") or COUNTRY_ISO.get(str(r.get("country", "")).strip(), "")
    return out


def get_customer_products(deps: Deps, customer_id: str) -> dict[str, Any]:
    rows = deps.sql.query("customer_products", {"customer_id": customer_id})
    out = [{k: r.get(k) for k in ("product_id", "product_type", "currency", "current_balance", "credit_limit", "days_past_due", "product_status")} for r in rows]
    for r in out:  # gold.customer_products trae el nombre del dataset ("Tarjeta Crédito"); el catálogo, el canónico (credit_card). Puente: product_type_dataset (ADR-24)
        r["product_type"] = canonical_product_type(deps, r.get("product_type"))
    return {"products": out}


def canonical_product_type(deps: Deps, value: str | None) -> str | None:
    from agent.policy.engine import load_catalog
    if not value:
        return value
    cat = load_catalog(str(deps.settings.catalog_path)) if getattr(deps, "settings", None) else []
    by_dataset = {p.get("product_type_dataset"): p["product_type"] for p in cat if p.get("product_type_dataset")}
    return by_dataset.get(value, value)


SECTION_HINTS = {  # ontología ligera: la plantilla R1–R8 es fija, así que la pregunta se enruta a su sección
    "R2": r"requisit|necesito|piden|exigen|\bcondicion|puntaje|pontua",
    "R3": r"\btasa|\btaxa|inter[eé]s|juros|\bcat\b|\bcft\b|\btea\b|\btna\b|\bcet\b|usura|costo|custo|\bea\b",
    "R4": r"monto|valor|plazo|prazo|cuota|parcela|m[aá]ximo|m[ií]nimo|cu[aá]nto|quanto",
    "R5": r"proceso|processo|c[oó]mo (pido|solicito|funciona)|pasos|etapas",
    "R6": r"datos|dados|consentim|privacid|autoriz",
    "R7": r"reclam|queja|aprueba|aprova|\bhumano\b|\bpessoa\b|\bpersona\b|\basesor\b|\bassessor\b",
    "R8": r"significa|qu[eé] es (la )?mora|glosario|gloss[aá]rio|inadimpl",
    "R1": r"qu[eé] es|o que [eé]|para qui[eé]n|para quem",
}
JURISDICTION_TERMS = {"cft": "AR", "tna": "AR", "tea": "AR", "cat": "MX", "usura": "CO"}


def route_sections(query: str) -> list[str]:
    q = query.lower()
    return [rid for rid, pat in SECTION_HINTS.items() if re.search(pat, q)]


def jurisdiction_mismatch(query: str, country: str) -> str | None:
    """Devuelve el término de costo de otra jurisdicción si el cliente lo usa (p. ej. CFT con perfil CO)."""
    for term, cc in JURISDICTION_TERMS.items():
        if re.search(rf"\b{term}\b", query.lower()) and cc != country:
            return term.upper()
    return None


def search_policy(deps: Deps, query: str, country: str, language: str, product_code: str | None = None, top_k: int = 5) -> dict[str, Any]:
    """Híbrido: vectorial + léxico fusionados por RRF; bonus a las secciones que la pregunta pide. Mismo contrato en Cosmos (hybrid search)."""
    filters = {"country": country, "language": language}
    if product_code:
        filters["product_code"] = product_code
    embed_version, fallback = deps.embed.model_version, False
    try:
        vec = deps.embed.embed([query])[0]
        vec_hits = deps.store.search(vec, filters, k=top_k * 3)
    except Exception as e:  # noqa: BLE001 — endpoint frío (scale-to-zero), 403 o red: se sigue solo con léxico + enrutado y queda en la traza
        import logging
        logging.warning("search_policy: embed no disponible (%s: %s); búsqueda léxica", type(e).__name__, str(e)[:120])
        vec_hits, embed_version, fallback = [], "lexical-fallback", True
    lex_hits = deps.store.search_text(query, filters, k=top_k * 3)
    wanted = set(route_sections(query))
    fused: dict[str, float] = {}
    rows: dict[str, dict[str, Any]] = {}
    for hits in (vec_hits, lex_hits):
        for rank, h in enumerate(hits, 1):
            fused[h["chunk_id"]] = fused.get(h["chunk_id"], 0.0) + 1.0 / (60 + rank)
            rows[h["chunk_id"]] = h
    for cid, r in rows.items():
        if r.get("rule_id") in wanted:
            fused[cid] += 1.0 / 30  # equivale a estar en el top-1 de una lista
    order = sorted(fused, key=lambda c: -fused[c])[:top_k]
    return {"chunks": [{**{k: rows[c].get(k) for k in ("chunk_id", "text", "rule_id", "version", "source", "product_code")}, "score": round(fused[c], 5)} for c in order],
            "embedding_model_version": embed_version, "embed_fallback": fallback, "sections_routed": sorted(wanted)}


def get_prescore(deps: Deps, customer_id: str) -> dict[str, Any]:
    prof = (deps.sql.query("customer_profile", {"customer_id": customer_id}) or [{}])[0]
    beh = (deps.sql.query("customer_behavior", {"customer_id": customer_id}) or [{}])[0]
    feats = {k: prof.get(k) for k in ("credit_score", "estimated_monthly_income", "segment", "country", "country_code")}
    feats.update({k: beh.get(k) for k in ("n_tx", "amount_usd_12m", "declined_ratio", "max_days_past_due", "active_months")})
    prods = deps.sql.query("customer_products", {"customer_id": customer_id})  # v2: cartera agregada, sin days_past_due (es el target del pre-score)
    loans = ("personal_loan", "mortgage", "payroll_loan", "Préstamo Personal", "Préstamo Hipotecario")
    feats.update({"n_products": len(prods), "n_active_products": sum(1 for p in prods if p.get("product_status") == "Active"),
                  "credit_limit_total": sum(float(p.get("credit_limit") or 0) for p in prods), "balance_total": sum(float(p.get("current_balance") or 0) for p in prods),
                  "n_cards": sum(1 for p in prods if p.get("product_type") in ("credit_card", "Tarjeta Crédito")), "n_loans": sum(1 for p in prods if p.get("product_type") in loans)})
    return deps.prescore.predict(feats)


def evaluate_eligibility_tool(deps: Deps, settings, customer_id: str, country: str, product_type: str, amount: float | None, prescore: dict[str, Any] | None) -> dict[str, Any]:
    prof = (deps.sql.query("customer_profile", {"customer_id": customer_id}) or [{}])[0]
    beh = (deps.sql.query("customer_behavior", {"customer_id": customer_id}) or [{}])[0]
    rates = deps.sql.query("regulator_rates", {"country": country, "product_type": product_type})
    return evaluate_eligibility(prof, beh, product_type, amount, prescore, country, settings.catalog_path, rates)


def create_handoff(deps: Deps, doc: dict[str, Any]) -> dict[str, Any]:
    from agent.handoff import validate_handoff
    validate_handoff(doc)
    deps.store.put_handoff(doc)
    return {"case_id": doc["case_id"]}
