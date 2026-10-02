# eval/ · harness de evaluación (ia-ml)

| Archivo | Qué mide | Cómo correr | Umbral |
| --- | --- | --- | --- |
| `retrieval_cases.jsonl` + `retrieval_eval.py` | Recall@5 del retrieval por idioma, con BM25 como baseline (ADR-06) | `python eval/retrieval_eval.py` | ≥ 0,8 es y pt; el embedding mock se reporta, el real bloquea |

Regla (ADR-21, acuerdo con Factored): ninguna fuente externa entra como caso, feature ni label; los casos se construyen con los usuarios de prueba y el catálogo sintético. Datos reales de Factored solo en `gold.intent_labels` y el pre-scoring, dentro de Databricks.
