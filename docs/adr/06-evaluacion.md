# 06-evaluacion

Owner: Manuela · v1 · 2026-09-28 · Fuente completa: ADR compartido (Claude Doc) y página "Plan IA/ML Agente Crédito".

Eval set 300 casos (40/25/25/10; ES 60/PT 40) en pares actuar/abstener. Componentes con baseline: clasificador (TF-IDF+LogReg), pre-score (regla y LogReg), retrieval (BM25), agente (LLM solo). Matriz de confusión de acción: Act/Abstain/Paired Accuracy, CAR, SR/UR/IRR, FP rate de acción, Injection Violation Rate, AbsRec@K. Casos adversariales etiquetados con MITRE ATLAS. Judge validado con 50 juicios humanos. Salida del harness en MLflow y CI.

Para ampliar este apartado usa el skill `adr-hackathon` (modo documentar).
