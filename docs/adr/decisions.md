# Decisiones (ADR-01…NN) · fuente: ADR compartido v1.2 · 2026-09-28 · ADR-18 añadida 2026-09-29

| ADR | Rol | Decisión | Alternativas descartadas | Criterio | Estado |
| --- | --- | --- | --- | --- | --- |
| 01 | ia-ml | Orquestación LangGraph: Understand → Decide → Act → Verify → Escalate | ReAct libre; framework propio | Explicita dónde no actuar; traza por nodo; test por nodo | cerrada |
| 02 | ia-ml | LLM vía Databricks Foundation Model APIs (Claude Sonnet; Llama 8B para clasificación) | Azure OpenAI; API Anthropic directa | Un plano de gobierno; sin salida del tenant | cerrada |
| 03 | ia-ml | RAG sobre corpus sintético de políticas y catálogo, chunk por regla con metadatos | Solo tabla products | El dataset no trae reglas; el reto exige política sintética etiquetada | cerrada |
| 04 | ia-ml | Vector store: Cosmos DB NoSQL free tier (DiskANN), versión C; Vector Search solo si sobran créditos; respaldo LanceDB/FAISS | Vector Search siempre; Qdrant; AI Search | < 2.000 chunks; un componente ya existente; 0 USD | cerrada |
| 05 | ia-ml | Motor de elegibilidad determinista: reglas YAML en Python; Elegible / No / Revisión humana | Reglas en el prompt | Decisión reproducible y auditable | cerrada |
| 06 | ia-ml | Pre-scoring LightGBM en Model Serving scale-to-zero, SHAP + intervalo; feature del motor, nunca decide | Solo LogReg; sin ML | Baselines: regla credit_score y LogReg | cerrada |
| 07 | ia-ml | Clasificador intención+acción con call_transcripts; baseline TF-IDF+LogReg; vs LLM zero-shot | Solo LLM | Routing determinista y evidencia ML | cerrada |
| 08 | ia-ml | Guardrails entrada (inyección, PII, idioma) y salida (groundedness) | Solo prompt | El prompt no es un control | cerrada |
| 09 | servicio/ia-ml | Estado, handoffs y vectores en Cosmos free tier (TTL 24 h); trazas MLflow + App Insights | Lakebase; Redis | Costo cero, un componente | cerrada |
| 10 | ia-ml | MLflow Evaluate; eval set held-out ES/PT; judge validado con 50 juicios; métricas en CI | Evaluación manual final | El reto puntúa evidencia | cerrada |
| 11 | ia-ml | PT: corpus, eval y clasificador bilingües; métricas por idioma | Traducir en runtime | Reportar la limitación es requisito | cerrada |
| 12 | servicio | Identidad mock JWT (customer_id, scopes, exp); customer_id solo del token | Documento en el chat | Un documento no prueba identidad | abierta (mock vs Entra) |
| 13 | ia-ml | Métrica de no agencia = matriz de confusión de acción con Act/Abstain/Paired Accuracy, CAR, SR/UR/IRR, FP rate, IVR, AbsRec@K; MITRE ATLAS aparte para amenazas | "MAT/MAD"; solo tasa de escalamiento | Métricas reconocidas; aíslan contención de capacidad | cerrada |
| 14 | ia-ml | Graph + harness + loop engineering; ontología ligera; Jev opcional | Agente libre | Costo casi nulo | abierta (Jev, jue 1) |
| 15 | todos | Observabilidad: un plano, cuatro dominios sobre ops.*; tablero AI/BI; sin consola propia | Admin console | El jurado puntúa trazas, no frontend | cerrada |
| 16 | ia-ml | Multilenguaje sin traducción; idioma en Understand y Respond; embeddings cross-lingual; glosario; país desde perfil | Traducir; fine-tuning | No se pierde contexto; PT medido donde falla | cerrada |
| 17 | ia-ml | Cuantización int8 solo embeddings/clasificador/reranker con go/no-go en PT | Cuantizar todo | Gana donde se nota en el servicio | cerrada |
| 18 | ia-ml | El agente (grafo LangGraph) corre en la Function App Flex Consumption; Databricks aporta Foundation Model APIs, Model Serving y MLflow, no un Agent Framework | Mosaic AI Agent Framework (agente como endpoint de Model Serving); Agent Bricks | Un runtime, junto a la API; sin endpoint de agente con costo fijo; mismo código en func start y en Azure | cerrada |
