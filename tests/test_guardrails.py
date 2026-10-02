"""Capa determinista: todos los adversariales del dev set disparan sin LLM; los normales no."""
import json
from pathlib import Path
from agent import guardrails
from agent.adapters.llm_fmapi import _content_text

CASES = [json.loads(l) for l in open(Path(__file__).resolve().parents[1] / "eval" / "cases.jsonl", encoding="utf-8")]


def test_adversariales_disparan_sin_llm():
    adv = [c for c in CASES if c["category"] == "adversarial"]
    miss = [c["case_id"] for c in adv if not guardrails.blocks(guardrails.scan(c["message"]))]
    assert adv and not miss, miss


def test_normales_no_disparan():
    fp = [c["case_id"] for c in CASES if c["category"] != "adversarial" and guardrails.blocks(guardrails.scan(c["message"]))]
    assert not fp, fp


def test_pii_sola_no_bloquea():
    assert guardrails.scan("mi correo es ana@mail.com") == ["pii"] and not guardrails.blocks(["pii"])


def test_content_lista_gpt_oss():
    c = [{"type": "reasoning", "summary": []}, {"type": "text", "text": '{"intent": "x"}'}]
    assert _content_text(c) == '{"intent": "x"}' and _content_text("a") == "a"
