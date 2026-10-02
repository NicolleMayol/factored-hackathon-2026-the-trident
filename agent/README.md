# agent/ · runtime del agente (ia-ml)

Grafo LangGraph Understand → Decide → Act → Verify → Escalate → Respond (ADR-01, ADR-18, ADR-21). Corre igual en local y en la Function App; cada dependencia tiene adaptador mock o real elegido por `AGENT_*`.

```
agent/
  config/settings.py   App Settings de contracts/infra.yaml + AGENT_* (mock|real)
  graph/state.py       estado = campos de contracts/handoff.schema.json + telemetría de ops.agent_turns
  graph/nodes.py       los 6 nodos; Decide sin LLM (policy/engine.py); Verify exige cita por cifra
  graph/build.py       grafo compilado; loop Verify→Act máx. 2
  policy/engine.py     policy.yaml × scopes × flags → acción; evaluate_eligibility (catálogo + reglas E01–E11)
  tools/               tools de contracts/tools.yaml con timeout 8 s (25 s una vez si la dependencia está cold)
  adapters/            llm | sql | store | embed | prescore | trace, versión mock y real
  handle.py            handle(message, session), confirm(action_id), healthz()
  function_app.py      rutas de contracts/api.yaml (JWT HS256 validado en código)
  auth.py              decode_token, require_scope
  prompts/             versionados; hash → ops.agent_turns.prompt_version
```

## Local
```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
pytest -q
python -m agent.devserver        # chat local en http://localhost:7071 (sin Azure Functions)
python -m agent.cli cliente_co_ok "¿Cuál es la tasa del préstamo personal?"
python -m agent.cli cliente_co_pt "Qual a taxa de juros do empréstimo pessoal?"
python -m agent.cli cliente_mx_cond "Quiero solicitar el crédito ya"
```
Con Azure Functions Core Tools: `func start` en la raíz (lee `local.settings.json`, fuera de git).

## Integración (ADR-21, checklist)
| Dependencia | Variable | Mock | Real |
| --- | --- | --- | --- |
| LLM | `AGENT_LLM` | reglas léxicas | FM APIs (`FM_ENDPOINT_MAIN/SMALL`) |
| SQL | `AGENT_SQL` | `data/mock/*.csv` | SQL Warehouse `wh-agent` (`sp-agent-ro`) |
| Vector store / handoffs | `AGENT_STORE` | `policy_chunks.jsonl` + memoria | Cosmos `policy_chunks`, `handoffs` |
| Embeddings | `AGENT_EMBED` | hashing 1024 dims | Model Serving `embed-bge-m3` |
| Pre-scoring | `AGENT_PRESCORE` | función monótona | Model Serving `prescore-lgbm` |
| Trazas | `AGENT_TRACE` | `data/mock/ops_agent_turns.jsonl` | MLflow Tracing + `ops.agent_turns` |
