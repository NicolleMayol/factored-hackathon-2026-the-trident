"""Tools tipadas según contracts/tools.yaml. customer_id SIEMPRE sale del JWT. Cada tool devuelve dict serializable y lleva timeout/retries en el ejecutor."""
from __future__ import annotations
import concurrent.futures as cf
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


def get_customer_profile(deps: Deps, customer_id: str) -> dict[str, Any]:
    rows = deps.sql.query("customer_profile", {"customer_id": customer_id})
    if not rows:
        return {"found": False}
    r = rows[0]
    # nunca se devuelven columnas excluidas ni documento
    return {"found": True, **{k: r.get(k) for k in ("customer_id", "country", "segment", "credit_score", "estimated_monthly_income", "customer_status", "detected_accent")}}


def get_customer_products(deps: Deps, customer_id: str) -> dict[str, Any]:
    rows = deps.sql.query("customer_products", {"customer_id": customer_id})
    return {"products": [{k: r.get(k) for k in ("product_id", "product_type", "currency", "current_balance", "credit_limit", "days_past_due", "product_status")} for r in rows]}


def search_policy(deps: Deps, query: str, country: str, language: str, product_code: str | None = None, top_k: int = 5) -> dict[str, Any]:
    vec = deps.embed.embed([query])[0]
    filters = {"country": country, "language": language}
    if product_code:
        filters["product_code"] = product_code
    hits = deps.store.search(vec, filters, k=top_k)
    return {"chunks": [{k: h.get(k) for k in ("chunk_id", "text", "rule_id", "version", "score", "source", "product_code")} for h in hits],
            "embedding_model_version": deps.embed.model_version}


def get_prescore(deps: Deps, customer_id: str) -> dict[str, Any]:
    prof = (deps.sql.query("customer_profile", {"customer_id": customer_id}) or [{}])[0]
    beh = (deps.sql.query("customer_behavior", {"customer_id": customer_id}) or [{}])[0]
    feats = {k: prof.get(k) for k in ("credit_score", "estimated_monthly_income", "segment", "country")}
    feats.update({k: beh.get(k) for k in ("n_tx", "amount_usd_12m", "declined_ratio", "max_days_past_due", "active_months")})
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
