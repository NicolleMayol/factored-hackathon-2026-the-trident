# data/mock · datos sintéticos para desarrollo local (ia-ml)

Mismo esquema que `contracts/gold.yaml` y `contracts/chunks.yaml`. Ningún dato del dataset de Factored: todo es inventado. Se reemplaza por las tablas reales cambiando `AGENT_SQL=real` y `AGENT_STORE=real` (ADR-21).

| Archivo | Reemplazado por | Entregable |
| --- | --- | --- |
| `customer_360.csv`, `customer_products.csv`, `customer_behavior_12m.csv` (5 usuarios de prueba `TEST-*` + 45 sintéticos) | `hackathon.gold.*` | E1, E2 |
| `intent_labels.csv`, `contact_demand.csv` | `hackathon.gold.*` | E3, E4 |
| `credit_product_catalog.csv`, `catalog.yaml` | `gold.credit_product_catalog` + `policy/catalog.yaml` | E5 |
| `regulator_rates.csv` (valores aproximados, `source = MOCK`) | `hackathon.ref.regulator_rates` | E6 |
| `policy_chunks.jsonl` (plantilla R1–R8, 3 países × 3 productos × es/pt) | `gold.policy_chunks` → Cosmos `policy_chunks` | E7 |
| `ops_agent_turns.jsonl` (lo escribe el agente en local) | `hackathon.ops.agent_turns` | M8 |
