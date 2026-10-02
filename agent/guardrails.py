"""Guardrail determinista de entrada (ADR-04 P10, ADR-13): corre ANTES del LLM y no depende de él.

Dos capas: (1) estas regex, deterministas y auditables, en es/pt/en; (2) `guardrail_hits` del LLM en Understand (se unen).
Si la capa 1 dispara, Understand no llama al modelo: el mensaje no llega al LLM y la decisión es `block` por P10.
Etiquetas MITRE ATLAS: injection → AML.T0051 (prompt injection) / AML.T0054 (jailbreak); third_party → AML.T0057 (exfiltración vía LLM).
Medido en eval/cases.jsonl (IVR). Con el LLM real sin esta capa, IVR = 0,267 (it. 3); con ella, 0."""
from __future__ import annotations
import re

INJECTION = re.compile(
    r"(ignore\s+(all\s+)?(the\s+)?(previous|above|prior)\s+instructions"
    r"|ignora\s+(todas\s+)?(las|as)\s+instru[cç][õoi]+(nes|es)?"
    r"|system\s*prompt|prompt\s+del\s+sistema|prompt\s+do\s+sistema"
    r"|revela(r)?\s+(el|tu|o|seu)\s+prompt"
    r"|\bact\s+as\s+(the\s+)?(admin|system|bank\s+manager|manager)"
    r"|act[uú]a\s+como\s+(el\s+)?(admin|sistema|gerente)"
    r"|aja\s+como\s+(o\s+)?(admin|sistema|gerente)"
    r"|apru[eé]bame|aprova\s+(o\s+)?meu|approve\s+my)", re.I)

THIRD_PARTY = re.compile(
    r"(datos\s+de\s+(otro|otra|un|una)\s+cliente|datos\s+de\s+terceros|datos\s+de\s+mi\s+(vecino|jefe|esposo|esposa|hermano|hermana|amigo|amiga)"
    r"|dados\s+de\s+(outro|outra|um|uma)\s+cliente|dados\s+de\s+terceiros|dados\s+do\s+meu\s+(chefe|vizinho|marido|irm[ãa]o|amigo)|dados\s+da\s+minha\s+(chefe|vizinha|esposa|irm[ãa]|amiga)"
    r"|customer\s+list|lista\s+de\s+clientes|other\s+customer'?s?\s+data)", re.I)

PII = re.compile(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b|\b[\w.+-]+@[\w-]+\.[\w.]+\b")


def scan(message: str) -> list[str]:
    """Devuelve las etiquetas que disparan: subconjunto de {injection, third_party, pii}. Orden estable."""
    hits = []
    if INJECTION.search(message):
        hits.append("injection")
    if THIRD_PARTY.search(message):
        hits.append("third_party")
    if PII.search(message):
        hits.append("pii")
    return hits


def blocks(hits: list[str]) -> bool:
    """P10: inyección o datos de terceros bloquean; pii sola no (se redacta en el trace)."""
    return "injection" in hits or "third_party" in hits
