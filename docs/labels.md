# labels.md · M5 · etiquetado de `gold.intent_labels`

Owner: ia-ml · v1 · 2026-10-05 · acuerdo del PR #31 (opción 1 + 3): etiquetas auditables para lo que se pueda y declaración de que el dataset no distingue los cinco intents del workflow 4.

## Qué se etiqueta y por qué así

`call_transcripts.customer_text` son 42 frases plantilla repartidas sobre 171.321 transcripciones; `detected_intents` tiene un solo valor y `reason_category` no correlaciona con el texto (medición de datos, PR #31). Por eso `gold.intent_labels` se etiqueta **por texto**, una vez por frase, y se propaga; `es_entrenable = false`: propagar deja la misma frase en train y test, y las 42 no cubren `eligibility_simulation`, `formal_application` ni `disbursement`. La tabla sirve para demanda y trazabilidad; el clasificador de ADR-07 se entrena y evalúa con casos propios del workflow 4 (`ml/intent_classifier.py`, `ml/data/intents_train.jsonl` → `eval/cases.jsonl`), con la limitación declarada en ADR-07.

| Columna | Origen |
| --- | --- |
| `intent_label` | override manual de este documento; si no, el baseline TF-IDF+LogReg con confianza ≥ 0,6; si no, `out_of_scope` marcado `low_confidence` |
| `action_label` | `policy/policy.yaml`, acción por defecto con scopes completos: `product_info→answer`, `eligibility_simulation→confirm`, `formal_application→escalate`, `disbursement→escalate`, `out_of_scope→clarify` |
| `label_source` | `manual` · `model` · `low_confidence` |

Reproducible: `python ml/fetch_phrases.py` y `python ml/label_phrases.py data/ref/customer_text_phrases.csv` (ambos archivos ignorados por git: las filas del dataset no salen del workspace, ADR-12). Lo que entra al repo es la regla, no las frases: datos (E3) aplica los overrides por prefijo de este documento en el pipeline, escribe `label_source = 'manual'` y `es_entrenable = false`.

## Lo que hay en el dataset (medido el 5 oct con `ml/fetch_phrases.py`)

Las 42 frases distintas son **dos aperturas** con combinaciones de cuatro muletillas ("Perfecto, eso es lo que necesitaba", "Entiendo, muchas gracias", "¿Y eso cuánto tiempo tarda?", "Muy bien, ¿hay algo más que deba saber?"):

| Apertura | Qué pide | intent_label | action_label |
| --- | --- | --- | --- |
| "Buenas tardes, necesito consultar el saldo de mi tarjeta de crédito." | saldo de tarjeta | `out_of_scope` | `clarify` |
| "Hola, buenos días. Quisiera saber cuál es mi saldo actual en mi cuenta de ahorros." | saldo de cuenta | `out_of_scope` | `clarify` |

Ninguna habla de información de producto, elegibilidad, solicitud ni desembolso: el dataset no contiene el workflow 4. Por eso `es_entrenable = false` y el clasificador se mide con casos propios (ADR-07, ADR-21 §4c).

## Overrides

Frases cuyo intent se fija a mano (ganan al modelo). Coinciden por igualdad o por prefijo; se auditan en el PR.

| customer_text | intent_label |
| --- | --- |
| Buenas tardes, necesito consultar el saldo de mi tarjeta de crédito. | out_of_scope |
| Hola, buenos días. Quisiera saber cuál es mi saldo actual en mi cuenta de ahorros. | out_of_scope |

## Tabla de etiquetas

<!-- tabla:inicio -->
(la tabla completa se genera en local o en Databricks con `ml/label_phrases.py`; no se versiona: 42 filas, todas `out_of_scope` → `clarify`, fuente `manual` por prefijo)
<!-- tabla:fin -->
