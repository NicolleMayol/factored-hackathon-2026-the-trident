"""Nodos del grafo: Understand → Decide → Act → Verify → Escalate → Respond. Cada nodo recibe deps por inyección."""
from __future__ import annotations
import hashlib
import re
import uuid
from pathlib import Path
from typing import Any

from agent.adapters import Deps
from agent.config.settings import Settings
from agent.graph.state import AgentState
from agent.policy import engine
from agent import guardrails
from agent import tools as T

REQUIRED_SLOTS = {"eligibility_simulation": ["product_type"]}
COUNTRY_BY_LOCALE = {"es-MX": "MX", "es-CO": "CO", "es-AR": "AR", "pt-BR": "BR"}
COUNTRY_BY_NAME = {"Mexico": "MX", "Colombia": "CO", "Argentina": "AR", "Brasil": "BR", "Brazil": "BR"}
PCT_RE = re.compile(r"\d+(?:[.,]\d+)?\s?%")
NUM_RE = re.compile(r"\d[\d.,]*")
FORBIDDEN = re.compile(r"(aprobad[oa]|garantiz|te aprueb|aprovad[oa]|garanti[dr]|pré-aprovad|preaprobad)", re.I)


CITE_RE = re.compile(r"\[[^\]]{3,60}\]")


def _nums(text: str) -> set[str]:
    text = CITE_RE.sub(" ", text or "")  # los ids citados ([POL-CO-PL-01-es-v1-R3]) no son cifras
    return {n.strip(".,").replace(".", "").replace(",", "") for n in NUM_RE.findall(text)} - {""}


def llm_reply_grounded(reply: str, allowed_text: str) -> tuple[bool, str]:
    """Toda cifra de la respuesta del LLM debe existir en citas/hechos/borrador; sin promesas de aprobación."""
    extra = _nums(reply) - _nums(allowed_text)
    if extra:
        return False, f"numbers_not_in_facts:{sorted(extra)[:3]}"
    if FORBIDDEN.search(reply):
        return False, "forbidden_phrase"
    if len(reply.strip()) < 20:
        return False, "too_short"
    return True, ""


def _prompt(settings: Settings, name: str) -> tuple[str, str]:
    p: Path = settings.prompts_dir / name
    txt = p.read_text(encoding="utf-8")
    return txt, hashlib.sha256(txt.encode()).hexdigest()[:12]


class Nodes:
    def __init__(self, deps: Deps, settings: Settings):
        self.d, self.s = deps, settings

    # 1 ------------------------------------------------------------------
    def understand(self, st: AgentState) -> AgentState:
        tmpl, ver = _prompt(self.s, self.s.understand_prompt)
        pre = guardrails.scan(st["message"])  # capa 1: determinista, antes del modelo
        if guardrails.blocks(pre):
            lang = st.get("language") or ("pt" if st.get("locale", "").startswith("pt") else "es")
            with self.d.trace.span("understand", guardrail="deterministic"):
                pass
            return {**st, "intent": "out_of_scope", "intent_confidence": 1.0, "slots": {}, "guardrail_hits": pre, "language": lang,
                    "country": st.get("country") or COUNTRY_BY_LOCALE.get(st.get("locale", ""), "MX"),
                    "node_path": st.get("node_path", []) + ["understand"], "prompt_version": ver, "_mixed_language": False}
        with self.d.trace.span("understand"):
            out = self.d.llm.complete(tmpl.replace("{{message}}", st["message"]), {"task": "understand"}, model="small")
        u = getattr(self.d.llm, "last_usage", {}) or {}
        st = {**st, "tokens_in": st.get("tokens_in", 0) + u.get("tokens_in", 0), "tokens_out": st.get("tokens_out", 0) + u.get("tokens_out", 0), "cost_usd": round(st.get("cost_usd", 0.0) + u.get("cost_usd", 0.0), 6)}
        lang = out.get("language") or st.get("language") or ("pt" if st.get("locale", "").startswith("pt") else "es")  # sin señal clara, idioma del perfil
        return {**st, "intent": out["intent"], "intent_confidence": float(out.get("intent_confidence", 0)),
                "slots": out.get("slots", {}), "guardrail_hits": sorted(set(pre) | set(out.get("guardrail_hits", []))), "language": lang,
                "country": st.get("country") or COUNTRY_BY_LOCALE.get(st.get("locale", ""), "MX"),
                "node_path": st.get("node_path", []) + ["understand"], "prompt_version": ver,
                "_mixed_language": bool(out.get("mixed_language"))}

    # 2 ------------------------------------------------------------------
    def decide(self, st: AgentState) -> AgentState:
        hits = st.get("guardrail_hits", [])
        prof = {}
        if "customer:read" in st.get("scopes", []):
            prof = (self.d.sql.query("customer_profile", {"customer_id": st["customer_id"]}) or [{}])[0]
        prods = self.d.sql.query("customer_products", {"customer_id": st["customer_id"]}) if prof else []
        ctx = {
            "intent": st.get("intent"), "intent_confidence": st.get("intent_confidence"), "mixed_language": st.get("_mixed_language"),
            "scopes": st.get("scopes", []), "jwt_valid": True,
            "missing_required_slots": any(k not in st.get("slots", {}) for k in REQUIRED_SLOTS.get(st.get("intent", ""), [])),
            "clarifications": sum(1 for h in st.get("history", []) if h.get("action") == "clarify"),
            "days_past_due": max([int(p.get("days_past_due") or 0) for p in prods], default=0),
            "customer_status": prof.get("customer_status"), "fraud_flag": False,
            "injection_detected": "injection" in hits, "third_party_data_request": "third_party" in hits,
        }
        with self.d.trace.span("decide"):
            dec = engine.decide(ctx, self.s.policy_path)
        # scope insuficiente para la intención → escalar por scope
        reason = dec.reason_code
        action = dec.action
        if st.get("intent") == "eligibility_simulation" and "credit:simulate" not in st.get("scopes", []):
            action, reason = "escalate", "out_of_scope"
        esc = "none"
        if action == "escalate":
            esc = "scope" if reason == "out_of_scope" and st.get("intent") == "eligibility_simulation" else "policy"
        if action == "block":
            esc = "guardrail"
        # el país es el del perfil del cliente (jurisdicción), no el del idioma
        country = prof.get("country_code") or COUNTRY_BY_NAME.get(prof.get("country", ""), st.get("country"))
        return {**st, "country": country, "action": engine.ACTION_TO_API[action], "_policy_action": action, "rules_fired": dec.rules_fired,
                "reason_code": reason or "out_of_scope", "allowed_tools": dec.allowed_tools, "escalate_reason": esc,
                "node_path": st["node_path"] + ["decide"], "_profile": prof, "_products": prods}

    # 3 ------------------------------------------------------------------
    def act(self, st: AgentState) -> AgentState:
        if st.get("_policy_action") not in ("auto", "confirm"):
            return {**st, "tool_results": st.get("tool_results", {}), "tools_called": st.get("tools_called", []), "node_path": st["node_path"] + ["act"]}
        results: dict[str, Any] = dict(st.get("tool_results", {}))
        called = list(st.get("tools_called", []))
        cold_used: set[str] = set(st.get("_cold_used", []))
        cid, country, lang = st["customer_id"], st["country"], st["language"]
        slots = st.get("slots", {})
        try:
            for tool in st["allowed_tools"]:
                if tool in results:
                    continue
                with self.d.trace.span("tool", tool=tool):
                    if tool == "get_customer_profile":
                        results[tool] = T.run_tool(tool, lambda: T.get_customer_profile(self.d, cid), self.d, self.s, cold_used=cold_used)
                    elif tool == "get_customer_products":
                        results[tool] = T.run_tool(tool, lambda: T.get_customer_products(self.d, cid), self.d, self.s, cold_used=cold_used)
                    elif tool == "search_policy":
                        pcode = self._product_code(country, slots.get("product_type"))
                        results[tool] = T.run_tool(tool, lambda: T.search_policy(self.d, st["message"], country, lang, pcode), self.d, self.s, cold_used=cold_used)
                    elif tool == "get_prescore":
                        results[tool] = T.run_tool(tool, lambda: T.get_prescore(self.d, cid), self.d, self.s, cold_used=cold_used)
                    elif tool == "evaluate_eligibility":
                        results[tool] = T.run_tool(tool, lambda: T.evaluate_eligibility_tool(self.d, self.s, cid, country, slots.get("product_type", "personal_loan"), slots.get("amount"), results.get("get_prescore")), self.d, self.s, cold_used=cold_used)
                    called.append(tool)
        except T.ToolTimeout:
            return {**st, "tool_results": results, "tools_called": called, "action": "escalate", "_policy_action": "escalate",
                    "reason_code": "missing_data", "escalate_reason": "timeout_tool", "node_path": st["node_path"] + ["act"], "_cold_used": list(cold_used)}
        return {**st, "tool_results": results, "tools_called": called, "iterations": st.get("iterations", 0) + 1,
                "node_path": st["node_path"] + ["act"], "_cold_used": list(cold_used)}

    def _product_code(self, country: str, product_type: str | None) -> str | None:
        if not product_type:
            return None
        from agent.policy.engine import load_catalog
        for p in load_catalog(str(self.s.catalog_path)):
            if p["country"] == country and p["product_type"] == product_type:
                return p["product_code"]
        return None

    # 4 ------------------------------------------------------------------
    def verify(self, st: AgentState) -> AgentState:
        """Groundedness determinista: toda cifra que vaya a la respuesta debe salir de un chunk, una regla o una tool.
        Comprueba además que la tasa citada no supere el tope del país y que el dato no esté viejo (ops.dq_results)."""
        if st.get("_policy_action") not in ("auto", "confirm"):
            return {**st, "verify_ok": True, "citations": [], "verified_facts": [], "verify_notes": [], "node_path": st["node_path"] + ["verify"]}
        tr = st.get("tool_results", {})
        cits: list[dict[str, str]] = []
        facts: list[dict[str, str]] = []
        notes: list[str] = []
        sp = tr.get("search_policy", {})
        routed = set(sp.get("sections_routed", []))
        seen: set[str] = set()
        for c in sp.get("chunks", []):
            key = (c.get("product_code"), c.get("rule_id"))
            if key in seen:
                continue  # un chunk por producto y sección
            seen.add(key)
            cits.append({"type": "chunk", "id": c["chunk_id"], "text": c["text"]})
            if len(cits) >= 3:
                break
        if routed and not any(c["id"].endswith(tuple(f"-{r}" for r in routed)) for c in cits if c["type"] == "chunk"):
            notes.append("no_citation")  # la pregunta pide una sección y ninguna cita la cubre
        ev = tr.get("evaluate_eligibility")
        if ev:
            for r in ev["rules_fired"]:
                cits.append({"type": "rule", "id": r, "text": ""})
            if ev.get("product"):
                p = ev["product"]
                facts.append({"fact": f"tasa {p['rate_min']}–{p['rate_max']} % · monto {p['amount_min']}–{p['amount_max']} · plazo ≤ {p['term_months_max']} m", "source": f"catalog:{p['product_code']}"})
                cap = engine.regulatory_cap(self.d.sql.query("regulator_rates", {"country": st["country"], "product_type": st.get("slots", {}).get("product_type", "personal_loan")}), st["country"], st.get("slots", {}).get("product_type", "personal_loan"))
                if cap is not None and float(p["rate_max"]) > cap:
                    notes.append("rate_above_cap")
        for name in ("get_prescore",):
            if name in tr:
                cits.append({"type": "tool", "id": name, "text": ""})
                facts.append({"fact": f"probabilidad preliminar {tr[name]['probability']} (IC {tr[name]['ci_low']}–{tr[name]['ci_high']})", "source": f"tool:{name}@{tr[name]['model_version']}"})
        if st.get("intent") == "product_info" and not any(c["type"] == "chunk" for c in cits):
            notes.append("no_citation")
        ok = not notes
        return {**st, "verify_ok": ok, "citations": cits, "verified_facts": facts, "verify_notes": notes, "node_path": st["node_path"] + ["verify"]}

    # 5 ------------------------------------------------------------------
    def escalate(self, st: AgentState) -> AgentState:
        from agent.handoff import build_handoff
        reason = st.get("reason_code") or "out_of_scope"
        if reason not in ("regulatory", "missing_data", "borderline", "out_of_scope", "injection_suspected", "risk_flag"):
            reason = "out_of_scope"
        doc = build_handoff(st, reason)
        with self.d.trace.span("tool", tool="create_handoff"):
            T.create_handoff(self.d, doc)
        esc = st.get("escalate_reason") or "policy"
        if esc == "none":
            esc = "no_citation" if "no_citation" in st.get("verify_notes", []) else "policy"
        return {**st, "case_id": doc["case_id"], "action": "escalate", "escalate_reason": esc, "tools_called": st.get("tools_called", []) + ["create_handoff"], "node_path": st["node_path"] + ["escalate"]}

    # 6 ------------------------------------------------------------------
    def respond(self, st: AgentState) -> AgentState:
        lang = st.get("language", "es")
        tmpl, ver = _prompt(self.s, f"respond_{lang}_{self.s.respond_prompt_version}.md")
        a = st.get("action")
        tr = st.get("tool_results", {})
        if a == "blocked":
            reply = {"es": "No puedo atender esa solicitud.", "pt": "Não posso atender essa solicitação."}[lang]
        elif a == "reject":
            reply = {"es": "Tu sesión no es válida. Inicia sesión de nuevo.", "pt": "Sua sessão não é válida. Entre novamente."}[lang]
        elif st.get("_policy_action") == "abstain":
            reply = {"es": "Puedo ayudarte con información y pre-evaluación de productos de crédito: préstamo personal, tarjeta de crédito y crédito de libranza. ¿Sobre cuál quieres saber?",
                     "pt": "Posso ajudar com informação e pré-avaliação de produtos de crédito: empréstimo pessoal, cartão de crédito e crédito consignado. Sobre qual você quer saber?"}[lang]
        elif a == "clarify":
            reply = {"es": "¿Sobre qué producto quieres información: préstamo personal, tarjeta de crédito o crédito de libranza?",
                     "pt": "Sobre qual produto você quer informação: empréstimo pessoal, cartão de crédito ou crédito consignado?"}[lang]
        elif a == "escalate":
            reply = {"es": f"Esto lo revisa un asesor. Te dejo el caso {st.get('case_id')} con todo el contexto; te contactan en el canal que elegiste.",
                     "pt": f"Isso será revisado por um assessor. Deixei o caso {st.get('case_id')} com todo o contexto; eles entram em contato pelo canal que você escolheu."}[lang]
        elif st.get("intent") == "eligibility_simulation" and tr.get("evaluate_eligibility"):
            ev = tr["evaluate_eligibility"]
            p = ev["product"] or {}
            expl = ev["explanation_es"] if lang == "es" else ev["explanation_pt"]
            if a == "confirm" and not st.get("_confirmed"):
                reply = {"es": f"Puedo hacer una pre-evaluación no vinculante de {p.get('name_es','el producto')} con tus datos. ¿Autorizas que la haga? (sí / no)",
                         "pt": f"Posso fazer uma pré-avaliação não vinculante de {p.get('name_pt','o produto')} com seus dados. Você autoriza? (sim / não)"}[lang]
            else:
                reply = {"es": f"Resultado preliminar: {ev['outcome']}. Motivo: {expl}. {p.get('name_es','')}: tasa {p.get('rate_min')}–{p.get('rate_max')} % anual, plazo hasta {p.get('term_months_max')} meses. No es una oferta vinculante; la aprobación la hace un analista.",
                         "pt": f"Resultado preliminar: {ev['outcome']}. Motivo: {expl}. {p.get('name_pt','')}: taxa {p.get('rate_min')}–{p.get('rate_max')} % ao ano, prazo até {p.get('term_months_max')} meses. Não é uma oferta vinculante; a aprovação é feita por um analista."}[lang]
        else:
            routed = set(tr.get("search_policy", {}).get("sections_routed", []))
            chunks = [c for c in st.get("citations", []) if c["type"] == "chunk"]
            if routed:
                chunks = [c for c in chunks if c["id"].endswith(tuple(f"-{r}" for r in routed))] or chunks[:1]
            chunks = chunks[:2]
            body = " ".join(c["text"] for c in chunks) if chunks else ""
            term = T.jurisdiction_mismatch(st["message"], st.get("country", ""))
            if term and body:
                body = _jurisdiction_note(lang, st["country"], term) + " " + body
            reply = (body + ({"es": " Esta información es de referencia y no constituye una oferta.", "pt": " Esta informação é de referência e não constitui uma oferta."}[lang])) if body else {"es": "No encontré información verificable para responder; lo paso a un asesor.", "pt": "Não encontrei informação verificável para responder; vou encaminhar a um assessor."}[lang]
        source, fallback = "template", ""
        use_llm = self.s.respond_llm == "on" or (self.s.respond_llm == "auto" and self.s.agent_llm == "real")
        llm_eligible = a == "answer" or (st.get("intent") == "eligibility_simulation" and tr.get("evaluate_eligibility") and not (a == "confirm" and not st.get("_confirmed")))
        if use_llm and llm_eligible and "{{facts}}" in tmpl:
            facts_txt = "\n".join([f"[{c['id']}] {c['text']}" for c in st.get("citations", []) if c.get("text")] + [f"[{f['source']}] {f['fact']}" for f in st.get("verified_facts", [])])
            prompt = tmpl.replace("{{message}}", st["message"]).replace("{{facts}}", facts_txt or "(sin hechos)").replace("{{draft}}", reply)
            try:
                with self.d.trace.span("respond_llm"):
                    out = self.d.llm.complete(prompt, {"task": "respond"}, model="main")
                u = getattr(self.d.llm, "last_usage", {}) or {}
                st = {**st, "tokens_in": st.get("tokens_in", 0) + u.get("tokens_in", 0), "tokens_out": st.get("tokens_out", 0) + u.get("tokens_out", 0), "cost_usd": round(st.get("cost_usd", 0.0) + u.get("cost_usd", 0.0), 6)}
                cand = str(out.get("reply", "")).strip()
                ok, why = llm_reply_grounded(cand, facts_txt + " " + reply)
                if ok:
                    reply, source = cand, "llm"
                else:
                    source, fallback = "template_fallback", why
            except Exception as e:  # noqa: BLE001  — el LLM nunca bloquea la respuesta
                source, fallback = "template_fallback", type(e).__name__
        reply = _redact_pii(reply)
        if tmpl and st.get("country") and a == "answer" and ("%" in reply or "R3" in routed_for_disclosure(st)):
            reply += _disclosure(lang, st["country"])
        return {**st, "reply": reply, "reply_source": source, "_respond_fallback": fallback, "prompt_version": f"{st.get('prompt_version','')}+{ver}", "model_version": getattr(self.d.llm, 'model_version', ''),
                "node_path": st["node_path"] + ["respond"]}


def routed_for_disclosure(st: AgentState) -> set[str]:
    return set(st.get("tool_results", {}).get("search_policy", {}).get("sections_routed", []))


def _jurisdiction_note(lang: str, country: str, term: str) -> str:
    own = {"CO": {"es": "tasa efectiva anual (EA) con tope de usura", "pt": "taxa efetiva anual (EA) com teto de usura"},
           "MX": {"es": "CAT (Costo Anual Total)", "pt": "CAT (Custo Anual Total)"},
           "AR": {"es": "TNA, TEA y CFT", "pt": "TNA, TEA e CFT"}}
    where = {"CFT": "Argentina", "TNA": "Argentina", "TEA": "Argentina", "CAT": "México", "USURA": "Colombia"}[term]
    cname = {"CO": ("Colombia", "na Colômbia"), "MX": ("México", "no México"), "AR": ("Argentina", "na Argentina")}[country]
    return {"es": f"El {term} aplica en {where}; en {cname[0]} el costo se expresa como {own[country]['es']}.",
            "pt": f"O {term} aplica-se na {where}; {cname[1]} o custo é expresso como {own[country]['pt']}."}[lang]


def _disclosure(lang: str, country: str) -> str:
    d = {("es", "MX"): " Consulta el CAT informativo antes de contratar.", ("es", "CO"): " La tasa no supera la de usura vigente certificada por la Superintendencia Financiera.",
         ("es", "AR"): " TNA, TEA y CFT se informan según el BCRA.", ("pt", "MX"): " Consulte o CAT informativo antes de contratar.",
         ("pt", "CO"): " A taxa não supera a taxa de usura vigente.", ("pt", "AR"): " TNA, TEA e CFT são informados conforme o BCRA."}
    return d.get((lang, country), "")


def _redact_pii(text: str) -> str:
    text = re.sub(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b", "[correo]", text)
    text = re.sub(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b", "[teléfono]", text)
    return text
