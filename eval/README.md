# eval/ · harness de evaluación (ia-ml)

| Archivo | Qué mide | Cómo correr | Umbral |
| --- | --- | --- | --- |
| `cases.jsonl` + `run_eval.py` + `metrics.py` | matriz de confusión de acción por idioma y métricas de no agencia (`metrics.md`): Act/Abstain/Paired Accuracy, CAR, SR/UR/IRR, FP rate, IVR por técnica ATLAS; groundedness, latencia por nodo, costo por turno | `python eval/run_eval.py` → `eval/results/latest.json` | `metrics.py` THRESHOLDS; IVR = 0 |
| `retrieval_cases.jsonl` + `retrieval_eval.py` | Recall@5 del retrieval por idioma: híbrido (lo que usa el agente), embedding y BM25 (ADR-06) | `python eval/retrieval_eval.py` | ≥ 0,8 es y pt; el embedding mock se reporta, el real bloquea |
| `test_external_guard.py` | regla Factored: nada externo como feature, label ni caso | `pytest eval/test_external_guard.py` | 0 hallazgos |

Con mocks el harness da 1,0 en todo porque el LLM stub se afinó sobre estos casos; el número que cuenta es el de la iteración 4 con FM APIs (`AGENT_LLM=real python eval/run_eval.py`), y la comparación stub vs real sale del mismo `latest.json`.

Regla (ADR-21, acuerdo con Factored): ninguna fuente externa entra como caso, feature ni label; los casos se construyen con los usuarios de prueba y el catálogo sintético. Datos reales de Factored solo en `gold.intent_labels` y el pre-scoring, dentro de Databricks.
