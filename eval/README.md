# eval/ · harness de evaluación (ia-ml)

| Archivo | Qué mide | Cómo correr | Umbral |
| --- | --- | --- | --- |
| `cases.jsonl` + `run_eval.py` + `metrics.py` | matriz de confusión de acción por idioma y métricas de no agencia (`metrics.md`): Act/Abstain/Paired Accuracy, CAR, SR/UR/IRR, FP rate, IVR por técnica ATLAS; groundedness, latencia por nodo, costo por turno | `python eval/run_eval.py` → `eval/results/latest.json` | `metrics.py` THRESHOLDS; IVR = 0 |
| `retrieval_cases.jsonl` + `retrieval_eval.py` | Recall@5 del retrieval por idioma: híbrido (lo que usa el agente), embedding y BM25 (ADR-06) | `python eval/retrieval_eval.py` | ≥ 0,8 es y pt; el embedding mock se reporta, el real bloquea |
| `test_external_guard.py` | regla Factored: nada externo como feature, label ni caso | `pytest eval/test_external_guard.py` | 0 hallazgos |

**Dev set vs held-out.** `cases.jsonl` y `retrieval_cases.jsonl` son el dev set: los escribió ia-ml y el stub se afinó sobre ellos, por eso dan 1,0 con mocks. El held-out de ADR-10 es `gold.intent_labels` con split temporal (últimos 3 meses a test, E3): mensajes reales de clientes que nadie del equipo escribió, con `expected_action` derivada de `action_label`. Se corre una vez con prompts congelados (`python eval/run_eval.py --cases eval/heldout_cases.jsonl`, sáb 3) y ese es el número que se reporta; la comparación stub vs LLM real sale del mismo `latest.json`.

Regla (ADR-21, acuerdo con Factored): ninguna fuente externa entra como caso, feature ni label; los casos se construyen con los usuarios de prueba y el catálogo sintético. Datos reales de Factored solo en `gold.intent_labels` y el pre-scoring, dentro de Databricks.
