# Usuarios de prueba (M3) · owner: ia-ml · v1 · 2026-10-01

Los emite `POST /session` (servicio) como JWT HS256 con `customer_id`, `scopes` y `exp` de 30 min. Son identidades del dataset o sintéticas; ningún dato personal real. `customer_id` siempre sale del token, nunca del texto.

| Usuario | `customer_id` | País | Idioma | Scopes | Perfil esperado | Escenario que cubre |
| --- | --- | --- | --- | --- | --- | --- |
| `cliente_co_ok` | `TEST-CO-001` | CO | es | `customer:read`, `credit:simulate` | score alto, sin mora, 2 productos | caso normal: informa y pre-evalúa → Elegible |
| `cliente_mx_cond` | `TEST-MX-002` | MX | es | `customer:read`, `credit:simulate` | score medio, 1 producto, flag `kyc_pending` | banda condicionada: informa con disclosure CAT, pre-evaluación con condición |
| `cliente_ar_no` | `TEST-AR-003` | AR | es | `customer:read`, `credit:simulate` | mora reciente, 3 productos | No elegible con motivo y cita a regla; sin negación de crédito (escala si insiste) |
| `cliente_co_pt` | `TEST-CO-004` | CO | pt | `customer:read`, `credit:simulate` | score alto, residente CO que habla portugués | mismo grafo en pt; disclosure del país del perfil, no del idioma |
| `cliente_solo_lectura` | `TEST-MX-005` | MX | es | `customer:read` | cualquiera | sin `credit:simulate`: informa, no pre-evalúa; pide escalar si insiste |
| `analista` | `AGENT-001` | — | es | `handoff:read` | agente humano | `GET /handoff/{case_id}` y `GET /trace/{trace_id}`; sin acceso a `/chat` como cliente |

Los `customer_id` `TEST-*` existen en `gold.customer_360` como filas sintéticas (`es_sintetico = true`) con los perfiles de la tabla; las carga datos con E1 (jue 1). En local, en `data/mock/customer_360.csv`.
