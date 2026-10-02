# Comparación de endpoints FM · rol `small` · 2026-10-02 00:08

Mismo harness (`eval/run_eval.py`), mismos casos, `temperature=0`. Elección: mayor `paired_accuracy`, menor `fp_action_rate`, luego p95 y costo.

| endpoint | n | act_accuracy | abstain_accuracy | paired_accuracy | fp_action_rate | ur | ivr | exact_match | p50_ms | p95_ms | usd_turn | fallas | r429 | wall_s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| databricks-meta-llama-3-1-8b-instruct | 82 | 0.655 | 0.906 | 0.667 | 0.094 | 0.172 | 0.0 | 0.793 | 825.7 | 1503.7 | 5e-05 | 15 | 0 | 235 |
| databricks-gpt-oss-20b | 82 | 0.897 | 0.83 | 0.833 | 0.17 | 0.0 | 0.0 | 0.854 | 1738.8 | 3259.9 | 0.00039 | 12 | 0 | 311 |
| databricks-meta-llama-3-3-70b-instruct | 82 | 0.862 | 0.868 | 0.792 | 0.132 | 0.103 | 0.0 | 0.866 | 1174.1 | 1657.5 | 0.00027 | 11 | 0 | 252 |
| databricks-gpt-oss-120b | 82 | 0.759 | 0.868 | 0.708 | 0.132 | 0.034 | 0.0 | 0.829 | 2398.7 | 3513.0 | 0.00051 | 14 | 0 | 340 |

## Decisión (it. 3)

Understand corre con `databricks-meta-llama-3-3-70b-instruct` (menos fallas, p95 la mitad que gpt-oss, 0,0003 USD/turno). gpt-oss-20b gana en paired pero actúa cuando debe abstenerse en 17 % de los casos, el error grave en banca. IVR 0 en los cuatro porque el guardrail determinista corre antes del modelo.

| Prompt (70B) | Fallas | act_accuracy | abstain_accuracy | fp_action_rate | paired |
|---|---|---|---|---|---|
| understand_v1 | 11 | 0,862 | 0,868 | 0,132 | 0,792 |
| understand_v2 | 3 | 0,897 | 1,0 | 0,0 | 0,917 |

Fallas restantes de v2 (it. 4): EV-005 / EV-025 ("hasta cuánto" es información del producto, no simulación), EV-035 (reclamación = R7, `product_info`).
