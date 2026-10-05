"""Genera el corpus sintético de políticas (R1–R8) por país × producto × idioma y lo parte en chunks.

    python data/policy_docs/build_corpus.py            # escribe data/policy_docs/docs/*.md y data/mock/policy_chunks.jsonl

Fuente de cifras: policy/catalog.yaml (E5) y data/mock/regulator_rates.csv (E6, pendiente de apuntar al snapshot de data/ref/). Fuentes normativas: docs/adr/12-fuentes-externas.md.
E7 (datos) reproduce esta misma lógica como job y escribe gold.policy_chunks; el agente no distingue uno de otro.
"""
from __future__ import annotations
import csv
import json
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]
MOCK = ROOT / "data" / "mock"
OUT_DOCS = ROOT / "data" / "policy_docs" / "docs"
VERSION = "v1"
VALID = ("2025-07-01", "2026-12-31")
SNAPSHOT = "2025-06-30"

COUNTRY = {"CO": {"es": "Colombia", "pt": "Colômbia"}, "MX": {"es": "México", "pt": "México"}, "AR": {"es": "Argentina", "pt": "Argentina"}}
CUR_NAME = {"COP": {"es": "pesos colombianos", "pt": "pesos colombianos"}, "MXN": {"es": "pesos mexicanos", "pt": "pesos mexicanos"}, "ARS": {"es": "pesos argentinos", "pt": "pesos argentinos"}, "USD": {"es": "dólares", "pt": "dólares"}}  # USD: los productos de México en el dataset son USD, no MXN (ADR-23)

# Normas citadas en source (ADR-12 v2). URLs exactas; no se cargan en tabla.
SOURCES = {
    "CO": {"R3": ("Ley 1328/2009 (CO) · tasa de usura SFC", "https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=36841"),
           "R6": ("Ley 1581/2012 (CO)", "https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=49981"),
           "R7": ("Ley 1328/2009 (CO)", "https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=36841")},
    "MX": {"R3": ("CAT · CONDUSEF / Banxico SIE CF303", "https://www.banxico.org.mx/SieInternet/consultarDirectorioInternetAction.do?sector=18&accion=consultarCuadro&idCuadro=CF303&locale=es"),
           "R6": ("LFPDPPP (MX)", "https://www.diputados.gob.mx/LeyesBiblio/pdf/LFPDPPP.pdf"),
           "R7": ("CONDUSEF (MX)", "https://www.diputados.gob.mx/LeyesBiblio/pdf/LFPDPPP.pdf")},
    "AR": {"R3": ("Com. A 5460 BCRA (AR) · Régimen de Transparencia", "https://www.bcra.gob.ar/archivos/Pdfs/texord/t-ri-transpa.pdf"),
           "R6": ("Ley 25.326 (AR)", "https://servicios.infoleg.gob.ar/infolegInternet/anexos/60000-64999/64790/norma.htm"),
           "R7": ("Com. A 5460 BCRA (AR)", "https://www.bcra.gob.ar/archivos/Pdfs/texord/t-ri-transpa.pdf")},
}

# Disclosure de costo total por país (R3)
COST = {
    "CO": {"es": "La tasa es efectiva anual (EA) y nunca supera la tasa de usura vigente certificada por la Superintendencia Financiera{cap_es}.",
           "pt": "A taxa é efetiva anual (EA) e nunca supera a taxa de usura vigente certificada pela Superintendência Financeira{cap_pt}."},
    "MX": {"es": "Antes de contratar se informa el CAT (Costo Anual Total) con fines informativos y de comparación, conforme a CONDUSEF{cap_es}.",
           "pt": "Antes de contratar informa-se o CAT (Custo Anual Total) para fins informativos e de comparação, conforme a CONDUSEF{cap_pt}."},
    "AR": {"es": "Se informan TNA, TEA y CFT (Costo Financiero Total) según el Régimen de Transparencia del BCRA{cap_es}.",
           "pt": "Informam-se TNA, TEA e CFT (Custo Financeiro Total) conforme o Regime de Transparência do BCRA{cap_pt}."},
}
# La cifra del tope solo se escribe si la fila de ref.regulator_rates tiene fuente oficial; una fila PENDIENTE (valor provisional, ADR-24 v1.1) guarda el motor pero no se cita.
CAP_PHRASE = {"CO": ("; el tope vigente para esta modalidad es {cap} % EA", "; o teto vigente para esta modalidade é {cap} % EA"),
              "MX": ("; la referencia de mercado para esta modalidad es {cap} % de CAT", "; a referência de mercado para esta modalidade é {cap} % de CAT"),
              "AR": ("; la referencia de mercado de CFT para esta modalidad es {cap} %", "; a referência de mercado de CFT para esta modalidade é {cap} %")}
CAP_KIND = {"CO": "usura", "MX": "cat", "AR": "cft"}

GLOSSARY = {"es": "Glosario: tasa de interés (precio anual del crédito), cuota (pago periódico), plazo (meses del crédito), mora (atraso en el pago), desembolso (entrega del dinero), pre-evaluación (resultado preliminar no vinculante).",
            "pt": "Glossário: taxa de juros (preço anual do crédito), parcela (pagamento periódico), prazo (meses do crédito), inadimplência (atraso no pagamento), liberação (entrega do dinheiro), pré-avaliação (resultado preliminar não vinculante)."}


def fmt_money(v: float) -> str:
    return f"{int(v):,}".replace(",", ".")


def sections(p: dict, lang: str, cap: float | None) -> dict[str, str]:
    cc = p["country"]; name = p["name_es"] if lang == "es" else p["name_pt"]; cty = COUNTRY[cc][lang]; cur = CUR_NAME[p["currency"]][lang]
    cuota = fmt_money(float(p["amount_max"]) / p["term_months_max"] * (1 + float(p["rate_max"]) / 100 / 2))
    es_cap, pt_cap = ("", "")
    if cap is not None:
        es_cap, pt_cap = (t.format(cap=f"{cap:g}") for t in CAP_PHRASE[cc])
    if lang == "es":
        return {
            "R1": f"{name} en {cty}: producto de crédito para personas naturales clientes del banco. En este canal el agente informa condiciones y hace una pre-evaluación no vinculante; la aprobación, la negación y el cambio de condiciones los decide siempre un analista.",
            "R2": f"Requisitos de {name}: ser mayor de edad; ingreso mensual demostrable; antigüedad como cliente mayor a 6 meses; sin mora superior a 30 días en ningún producto; puntaje de crédito mínimo {p['min_score']}. Para la pre-evaluación se usan solo datos del propio cliente.",
            "R3": f"Tasa de {name}: entre {p['rate_min']} % y {p['rate_max']} % anual según perfil. " + COST[cc]["es"].format(cap_es=es_cap) + " La tasa definitiva se fija en la aprobación y no en el chat.",
            "R4": f"Montos y plazos de {name}: desde {fmt_money(p['amount_min'])} hasta {fmt_money(p['amount_max'])} {cur}; plazo hasta {p['term_months_max']} meses. Cuota de referencia para el monto máximo al plazo máximo y tasa máxima: aproximadamente {cuota} {cur} al mes.",
            "R5": f"Proceso para {name}: 1) pre-evaluación no vinculante en el chat con tu autorización; 2) solicitud formal con un asesor; 3) análisis y decisión de un analista; 4) desembolso. El chat no recibe solicitudes formales ni desembolsa.",
            "R6": "Consentimiento y datos: la pre-evaluación usa tus datos de cliente solo con tu autorización explícita en esta conversación; puedes revocarla en cualquier momento. No se consultan datos de terceros ni se comparten los tuyos con terceros.",
            "R7": "Revisión humana y reclamos: aprobar, negar o modificar condiciones de crédito lo hace una persona; si el chat no puede responder con certeza, escala el caso a un asesor con todo el contexto. Los reclamos se presentan por el canal de atención al consumidor financiero, que responde en los plazos de ley.",
            "R8": GLOSSARY["es"],
        }
    return {
        "R1": f"{name} em {cty}: produto de crédito para pessoas físicas clientes do banco. Neste canal o agente informa condições e faz uma pré-avaliação não vinculante; a aprovação, a negação e a mudança de condições são sempre decididas por um analista.",
        "R2": f"Requisitos de {name}: ser maior de idade; renda mensal comprovável; mais de 6 meses como cliente; sem atraso superior a 30 dias em nenhum produto; pontuação de crédito mínima {p['min_score']}. Para a pré-avaliação usam-se apenas dados do próprio cliente.",
        "R3": f"Taxa de juros de {name}: entre {p['rate_min']} % e {p['rate_max']} % ao ano conforme o perfil. " + COST[cc]["pt"].format(cap_pt=pt_cap) + " A taxa definitiva é fixada na aprovação e não no chat.",
        "R4": f"Valores e prazos de {name}: de {fmt_money(p['amount_min'])} até {fmt_money(p['amount_max'])} {cur}; prazo até {p['term_months_max']} meses. Parcela de referência para o valor máximo no prazo máximo e taxa máxima: aproximadamente {cuota} {cur} por mês.",
        "R5": f"Processo para {name}: 1) pré-avaliação não vinculante no chat com sua autorização; 2) solicitação formal com um assessor; 3) análise e decisão de um analista; 4) liberação. O chat não recebe solicitações formais nem libera valores.",
        "R6": "Consentimento e dados: a pré-avaliação usa seus dados de cliente apenas com sua autorização explícita nesta conversa; você pode revogá-la a qualquer momento. Não se consultam dados de terceiros nem se compartilham os seus com terceiros.",
        "R7": "Revisão humana e reclamações: aprovar, negar ou modificar condições de crédito é feito por uma pessoa; se o chat não puder responder com certeza, encaminha o caso a um assessor com todo o contexto. As reclamações são apresentadas pelo canal de atendimento ao consumidor financeiro, que responde nos prazos legais.",
        "R8": GLOSSARY["pt"],
    }


def build() -> list[dict]:
    cat = yaml.safe_load(open(ROOT / "policy" / "catalog.yaml", encoding="utf-8"))["products"]
    rates = list(csv.DictReader(open(MOCK / "regulator_rates.csv", encoding="utf-8")))
    OUT_DOCS.mkdir(parents=True, exist_ok=True)
    chunks = []
    for p in cat:
        # M10 (ADR-24): los 6 tipos del catálogo tienen R1–R8; el agente no ofrece lo que no puede citar
        cc = p["country"]
        cap = next((float(r["rate_max"]) for r in rates if r["country"] == cc and r["product_type"] == p["product_type"] and r["rate_kind"] == CAP_KIND[cc]
                    and r.get("rate_max") and not str(r.get("source", "")).upper().startswith("PENDIENTE")), None)
        for lang in ("es", "pt"):
            doc_id = f"POL-{cc}-{p['product_code']}-{lang}-{VERSION}"
            secs = sections(p, lang, cap)
            md = [f"# {doc_id}", f"producto: {p['product_code']} · país: {cc} · idioma: {lang} · versión: {VERSION} · vigencia: {VALID[0]} a {VALID[1]} · sintético: sí", ""]
            for rid, text in secs.items():
                src = SOURCES[cc].get(rid, ("catálogo sintético", ""))
                md += [f"## {rid}", text, f"<!-- source: {src[0]} -->", ""]
                chunks.append({"chunk_id": f"{doc_id}-{rid}", "doc_id": doc_id, "text": text, "text_es": text if lang == "es" else None, "text_pt": text if lang == "pt" else None, "language": lang, "country": cc, "product_code": p["product_code"],
                               "rule_id": rid, "version": VERSION, "valid_from": VALID[0], "valid_to": VALID[1], "source": src[0], "url": src[1],
                               "snapshot_date": SNAPSHOT, "es_sintetico": True, "embedding_model_version": "pending"})
            (OUT_DOCS / f"{doc_id}.md").write_text("\n".join(md), encoding="utf-8")
    with open(MOCK / "policy_chunks.jsonl", "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    return chunks


if __name__ == "__main__":
    ch = build()
    docs = {c["doc_id"] for c in ch}
    print(f"{len(docs)} documentos, {len(ch)} chunks → {MOCK / 'policy_chunks.jsonl'}")
