"""LLM stub: intención y slots por reglas léxicas; Verify y Respond deterministas. Sirve para tests y para correr sin FM APIs."""
from __future__ import annotations
import re
from typing import Any

INTENT_PATTERNS = {  # orden = prioridad; "proceso/cómo" e "hasta cuánto" son información, no acción
    "product_info_first": r"(proceso|c[oó]mo (es|funciona)|como funciona|hasta cu[aá]nto|at[eé] quanto|qu[eé] significa|o que significa)",
    "formal_application": r"\b(quiero|necesito|deseo|quero|preciso)\b.{0,25}\b(solicitar|aplicar|pedir|el cr[eé]dito ya|o empr[eé]stimo)|\bsolicitud formal\b|\bsolicitar (el|o) (cr[eé]dito|pr[eé]stamo|empr[eé]stimo)\b|\baplicar al\b",
    "disbursement": r"\b(desembols\w*|liber(ar|en|a|ación|ação)|cu[aá]ndo me (lo )?(depositan|desembolsan)|quando .*libera)\b",
    "eligibility_simulation": r"\b(califico|elegible|me aprueban|simula|cu[aá]nto me prestan|puedo acceder|tenho direito|consigo|simular|quanto posso|elegível)\b",
    "product_info": r"\b(tasa|inter[eé]s|requisitos|plazo|cuota|tarjeta|pr[eé]stamo|cr[eé]dito|libranza|taxa|juros|parcela|cart[aã]o|empr[eé]stimo|consignado|cat|cft|cet)\b",
}
PT_MARKERS = r"\b(você|vocês|não|obrigad[oa]|empréstimo|cartão|juros|taxa|quero|posso|tenho|consigo|parcelas|prazo|qual|quanto|preciso|dados|meu|minha|terceiros|aprova)\b"
ES_MARKERS = r"\b(usted|gracias|préstamo|tarjeta|interés|tasa|quiero|puedo|tengo|cuotas|plazo|cuál|cuánto|qué|hola)\b"
INJECTION = r"(ignore (all )?(previous|above) instructions|ignora (todas )?(las|as) instru[cç][oõi]+(nes|es)?|system prompt|revela(r)? (el|tu|o) prompt|act as|act[uú]a como (admin|sistema)|aprova meu|dame (los )?datos de (otro|otra) cliente|datos de terceros|dados de (outro|outra) cliente|dados de terceiros|customer list)"


class LLMMock:
    model_version = "mock-0"

    def __init__(self, settings=None):
        self.s = settings

    def complete(self, prompt: str, schema: dict | None = None, *, model: str = "main") -> dict[str, Any]:
        task = (schema or {}).get("task") if isinstance(schema, dict) else None
        text = prompt
        if task == "understand":
            return self._understand(text)
        if task == "verify":
            return {"ok": True, "notes": []}
        if task == "respond":
            return {"reply": text}
        return {"text": text}

    def _understand(self, text: str) -> dict[str, Any]:
        t = text.lower()
        pt = len(re.findall(PT_MARKERS, t))
        es = len(re.findall(ES_MARKERS, t))
        language = "pt" if pt > es else "es" if es > pt else None  # None → el nodo usa el idioma del perfil
        mixed = pt > 0 and es > 0 and abs(pt - es) <= 1
        hits = []
        if re.search(INJECTION, t):
            hits.append("injection")
        if re.search(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b|\b[\w.+-]+@[\w-]+\.[\w.]+\b", t):
            hits.append("pii")
        intent, conf = "out_of_scope", 0.5
        for name, pat in INTENT_PATTERNS.items():
            if re.search(pat, t):
                intent, conf = ("product_info" if name == "product_info_first" else name), 0.9
                break
        slots: dict[str, Any] = {}
        m = re.search(r"(\d[\d.,]{2,})\s*(pesos|usd|mxn|cop|ars|reais|r\$|\$)?", t)
        if m:
            slots["amount"] = float(m.group(1).replace(".", "").replace(",", "."))
        for code, pat in {"credit_card": r"tarjeta|cart[aã]o", "payroll_loan": r"libranza|consignado|n[oó]mina", "personal_loan": r"pr[eé]stamo personal|cr[eé]dito personal|empr[eé]stimo pessoal|pr[eé]stamo|empr[eé]stimo"}.items():
            if re.search(pat, t):
                slots["product_type"] = code
                break
        return {"intent": intent, "intent_confidence": conf, "language": language, "mixed_language": mixed,
                "slots": slots, "guardrail_hits": hits}
