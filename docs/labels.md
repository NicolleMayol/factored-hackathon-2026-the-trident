# labels.md · M5 · etiquetado de `gold.intent_labels`

Owner: ia-ml · v1 · 2026-10-05 · acuerdo del PR #31 (opción 1 + 3): etiquetas auditables para lo que se pueda y declaración de que el dataset no distingue los cinco intents del workflow 4.

## Qué se etiqueta y por qué así

`call_transcripts.customer_text` son 42 frases plantilla repartidas sobre 171.321 transcripciones; `detected_intents` tiene un solo valor y `reason_category` no correlaciona con el texto (medición de datos, PR #31). Por eso `gold.intent_labels` se etiqueta **por texto**, una vez por frase, y se propaga; `es_entrenable = false`: propagar deja la misma frase en train y test, y las 42 no cubren `eligibility_simulation`, `formal_application` ni `disbursement`. La tabla sirve para demanda y trazabilidad; el clasificador de ADR-07 se entrena y evalúa con casos propios del workflow 4 (`ml/intent_classifier.py`, `ml/data/intents_train.jsonl` → `eval/cases.jsonl`), con la limitación declarada en ADR-07.

| Columna | Origen |
| --- | --- |
| `intent_label` | override manual de este documento; si no, el baseline TF-IDF+LogReg con confianza ≥ 0,6; si no, `out_of_scope` marcado `low_confidence` |
| `action_label` | `policy/policy.yaml`, acción por defecto con scopes completos: `product_info→answer`, `eligibility_simulation→confirm`, `formal_application→escalate`, `disbursement→escalate`, `out_of_scope→clarify` |
| `label_source` | `manual` · `model` · `low_confidence` |

Reproducible: `python ml/label_phrases.py data/ref/customer_text_phrases.csv` escribe `docs/labels.csv` y la tabla de abajo. Datos (E3) propaga `docs/labels.csv` por `customer_text` y escribe `label_source` y `es_entrenable = false`.

## Overrides

Frases cuyo intent se fija a mano (ganan al modelo). Una por línea; se audita en el PR.

| customer_text | intent_label |
| --- | --- |
| (pendiente: se completa con las 42 frases de datos) | product_info |

## Tabla de etiquetas

<!-- tabla:inicio -->
(se genera con `ml/label_phrases.py` cuando datos entregue `data/ref/customer_text_phrases.csv`)
<!-- tabla:fin -->
