# Agente Crédito LATAM · Factored AI & Data Hackathon 2026
Versión en español: [README.es.md](README.es.md)

Customer service agent for a regional bank (Mexico, Colombia, Argentina), focused on one workflow: information about credit products and eligibility, in Spanish and Portuguese. It informs and simulates; it never makes a credit decision. It knows when not to act, and the numbers below show it. The ADRs and contracts referenced here are in Spanish.

## How it works
- State graph Understand → Decide → Act → Verify → Escalate (LangGraph) on an Azure Function App. Decide is deterministic: it uses the policy matrix in `policy/policy.yaml`, the token scopes and the customer flags.
- Three separate components: the LLM (conversation, Databricks Foundation Model APIs), a logistic regression pre-score (an input to the engine; it never decides) and versioned eligibility rules (the only source of the outcome).
- RAG over synthetic policies and a synthetic catalog (labeled as such), with the vector store and state in Azure Cosmos DB. Every figure in an answer traces back to a chunk or a tool result.
- Data: bronze/silver/gold medallion in Databricks (Unity Catalog) on the LATAM Bank dataset; schema, quality and freshness contracts live in `contracts/`.

## Where AI is used and where it is not
| Step | Who decides | Why |
| --- | --- | --- |
| Understand intent and language | Deterministic guardrail (es/pt/en regex) before the model; then Llama 3.3 70B with typed JSON output (`understand_v2`); TF-IDF + logistic regression baseline (macro-F1 0.92) | free-form language in es and pt; an injection never reaches the LLM |
| Decide what can be done | Versioned YAML rules × token scopes × regulatory band; no LLM | reproducible, auditable, grounded in each country's regulations |
| Execute | Typed tools, only the authorized ones; pre-score (logistic regression with portfolio features, AUC 0.78 on 134k customers) as an input | the model informs and never approves; it beat LightGBM on simplicity at equal AUC |
| Verify | Deterministic check: every figure must appear in a citation or a verified fact; Respond drafts the reply with Llama 3.3 70B and, if the check fails, answers with the template | no citation, no claim |
| Escalate (hand off to an advisor) | A human, always for the closed band (not eligible) | abstaining counts as a correct answer |

## Explicit trade-offs
| Axis | Decision | What we give up |
| --- | --- | --- |
| Autonomy | The agent informs and runs a pre-check; it never approves or denies credit | less automation "wow" |
| Accuracy | Every figure cites a chunk or a rule; rate ≤ usury cap, checked | shorter answers and more escalations |
| Latency | p95 ≤ 8 s warm (measured 9.7 s, see Evidence); cold start reported separately; scale-to-zero outside the evaluation window | slow first turn after idle time |
| Cost | Free tiers and serverless (version C, ≈ 35–125 USD / 7 days) | no always-on; RU/s limits |
| Human oversight | Handoff with full context and reason (`escalate_reason`); analyst view | some cases are not resolved in the chat |

## External sources and why we use them
The dataset includes customers, products and transactions, but not what regulation requires the bank to tell the customer (usury cap, CAT, CFT, reference TEA). Those public figures from BCRA, the Superintendencia Financiera de Colombia and Banxico come in by batch, with URL and snapshot date. They serve only as RAG context and as the ceiling for the rules engine. No external source is used for training or evaluation: metrics are computed on the dataset and a synthetic catalog, and a CI test checks this. Source-by-source detail is in `docs/adr/12-fuentes-externas.md`.

## Evidence (numbers as of October 5)
| What | How it was measured | Result |
| --- | --- | --- |
| Action confusion matrix, all real (Llama 3.3 70B, `understand_v2`, gold via SQL, traces, pre-score, Cosmos + `embed-bge-m3`) | 82 es/pt cases in act/abstain pairs, 15 MITRE ATLAS adversarial cases, users = real customers from gold (`eval/pick_users.py`, `eval/run_eval.py`) | act accuracy 0.86 · abstain accuracy 0.98 · paired 0.83 · action FP 0.019 · IVR 0 · groundedness 1.0 · exact match 0.915 · 5 intent edge-case failures · thresholds met · same numbers with store/embed on mock and on real (`search_policy` 3 ms → 1.2 s, no decision changes) |
| Same matrix with the fixture (`data/mock`, SQL on mock) | same 82 cases | act 0.90 · abstain 1.0 · FP 0 · 3 failures; the gap with the row above comes from LLM intent on edge-case messages, not from the data |
| Bug exposed by the real LLM | `¿Califico?` ("Do I qualify?") → the 70B returns `slots.product_type = null` and the agent treated the slot as filled (it confirmed instead of asking for clarification); the mock never returns null keys | fixed in Decide (P06); abstain 0.94 → 0.98, action FP 0.057 → 0.019 |
| Finding from the eval with real SQL | first run on gold: abstain 0.68, action FP 0.32 | the `TEST-*` customers in gold had no products or behavior, so P07 never fired; fixed by picking real customers per condition in the eval and by injecting the `TEST-*` products into `gold.customer_products` from the pipeline (`gold.py`) for the UI users |
| Deterministic guardrail | same 15 adversarial cases, with and without the regex layer before the LLM | IVR 0.267 → 0 on all 4 endpoints tested |
| Model comparison for Understand | same harness, 4 pay-per-token endpoints (`eval/models.md`) | llama-3.3-70b: fewer failures and half the p95 of gpt-oss; chosen on the numbers |
| Prompt v1 → v2 | 11 failures → 3, action FP 0.13 → 0 | the gain came from the prompt, not the model |
| Hybrid retrieval (vector + BM25 + RRF, routed by section) | 24 questions with an expected chunk (`eval/retrieval_eval.py`) | Recall@5 with bge-m3 fp32: ES 1.0 · PT 0.917 |
| Intent classifier (baseline) | TF-IDF char 2–5 + LogReg, 109 synthetic phrases → 60 unique held-out messages | macro-F1 0.92 (es 0.94 · pt 0.89); its errors are the ones the guardrail fixes |
| Pre-score | 134,037 real customers from gold; declared proxy target (no late payments > 30 d); 4 experiments in MLflow | logistic v1 0.66 → **v2 with portfolio 0.78**; LightGBM 0.66 → 0.78: the features are worth 0.12 AUC, the model 0 |
| Cost and latency per turn | 82 real eval turns from local, traces in `ops.agent_turns` | 0.00035 USD/turn · with store/embed on mock: p50 3.3 s · p95 9.7 s · with Cosmos + `embed-bge-m3` (after #69): p50 3.1 s · p95 10.7 s (`search_policy` ≈ 1.2 s; two calls to the 70B; ≈ 0.9 s per gold query); first turn ≈ 15–20 s when the warehouse or the Function is cold. Production numbers (10-user load test by service) replace these when measured |
| Deployed Function (`func-agent-bank-dev`, all real after #69) | `/api/healthz`; `POST /api/chat` as `cliente_co_pt` and `cliente_co_ok`; row in `ops.agent_turns` | 5 dependencies `ok`; PT turn answered with Cosmos citations (first turn after the apply: 20 s, Function + endpoint cold); ES turn warm: 4.7 s with 3 citations; trace recorded with `reply_source=llm` |
| `embed-bge-m3` deployment | two failed health checks (Small and Medium, "update timed out") | cause: the registered version carried a 3.4 GB `python_model.pkl` (cloudpickle) on top of the 2.2 GB artifact; re-registered as models-from-code (`ml/bge_m3_model.py`, v5) → READY in 13 min; CAN_QUERY granted to `sp-agent-ro` |
| Pre-score at runtime | same customer through the endpoint (`prescore-lgbm`) and in-process (`policy/prescore_logreg.json`) | exact parity (p = 0.969, same SHAP); cold endpoint > 25 s (controlled timeout), warm 5.5 s with the 3 gold queries; that is why production runs `prescore=local` |

## What's missing and why
| Piece | Status | Reason | What it would take |
| --- | --- | --- | --- |
| Embedding endpoint cost | `embed-bge-m3` runs without scale-to-zero during the evaluation window (ADR-21 §1) | a cold start takes minutes; the agent would fall back to lexical search (`embed_fallback`) and the demo would lose the vector | re-enable scale-to-zero after the evaluation (`ml/serving.py` without `--always-on`) |
| Held-out set from the dataset | not trainable: 42 template phrases under the 6 categories (`docs/labels.md`) | the dataset does not separate the five intents of workflow 4 | real labels from transcripts |
| CO and MX rate caps | provisional value, not cited | the SFC publishes a monthly PDF and Banxico an interactive query tool | paste two numbers per row (E6) |
| Portuguese in the dataset | 100% Spanish | the dataset is MX/CO/AR | PT is measured with a synthetic corpus and synthetic cases, stated as such |

## Documentation
| What | Where |
| --- | --- |
| Architecture decisions (ADR-01…NN) | `docs/adr/decisions.md` and `docs/adr/*.md` |
| Contracts: gold tables, tools, API, handoff, chunks, telemetry, infra | `contracts/` |
| Policy matrix and ES↔PT glossary | `policy/` |
| Diagrams (draw.io source and exports) | `diagrams/` |
| Team dependencies and schedule | `docs/adr/dependencies.md` |
| Test customers and analyst user | `docs/test-users.md` |
| Dataset insights (credit demand by country and language, segments) | `data/` (notebook E10) |

## Running it
Setup, deployment and reproducible evaluation instructions are in `docs/adr/09-servicio.md` and `docs/adr/06-evaluacion.md` (to be completed during the sprint).

## Team
Eladio Yovera (data) · Manuela Larrea (AI/ML) · Nicolle Mayol (service). Documentation as code: every decision goes in through a PR with an impact analysis (`AGENTS.md`, `.claude/skills/adr-hackathon`).
