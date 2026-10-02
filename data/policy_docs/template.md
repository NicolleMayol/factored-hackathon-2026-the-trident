# Plantilla de documento de política · R1–R8 (ia-ml, ADR-03)

Un documento por `country × product_code × language`. `doc_id = POL-<país>-<product_code>-<lang>-v<n>`; un chunk por sección, `chunk_id = <doc_id>-R<1..8>`. Todo documento es sintético (`es_sintetico = true`); las cifras salen de `gold.credit_product_catalog` y los topes de `ref.regulator_rates`; las secciones R3, R6 y R7 citan la norma del país en `source` (ADR-12).

| Sección | rule_id | Contenido obligatorio | source |
| --- | --- | --- | --- |
| Qué es | R1 | nombre, país, para quién, qué hace el agente (informa y simula; nunca aprueba) | catálogo sintético |
| Requisitos | R2 | edad, ingreso demostrable, antigüedad, mora máxima, puntaje mínimo | catálogo sintético |
| Tasa y costo total | R3 | rango de tasa anual del catálogo, tope regulatorio vigente, métrica de costo total del país (CAT / CFT / EA) | norma del país |
| Montos y plazos | R4 | mínimo, máximo, moneda, plazo máximo, cuota de referencia | catálogo sintético |
| Proceso | R5 | pre-evaluación no vinculante en el chat → solicitud formal → análisis humano → desembolso | catálogo sintético |
| Consentimiento y datos | R6 | autorización explícita para usar datos del cliente, revocación, no se comparten con terceros | ley de datos del país |
| Revisión humana y reclamos | R7 | qué decide siempre una persona, cómo escalar, canal de reclamos | norma de protección al consumidor |
| Glosario | R8 | términos del producto en el idioma del documento (policy/glossary.yaml) | glosario |

Reglas de redacción: frases cortas; cada cifra aparece una sola vez y es la del catálogo; sin nombres de bancos reales; sin promesas de aprobación; en portugués se usan los términos del glosario (taxa de juros, parcelas, prazo, CET) y se mantiene la jurisdicción del país del perfil.
