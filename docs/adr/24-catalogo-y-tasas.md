# 24-catalogo-y-tasas

Owner: Eladio · v1 · 2026-10-02.

## ADR-24 · Catálogo sintético y tasas de regulador (E5 y E6)  ·  rol: datos  ·  2026-10-02  ·  estado: cerrada

**Decisión.** El catálogo (`policy/catalog.yaml`) y las tasas de regulador (`ref.regulator_rates`) se **generan con un script y se versionan**, no se escriben a mano: Argentina sale de la API del BCRA, Colombia y México de percentiles del dataset, y cada cifra lleva su fuente.

Dos artefactos, dos scripts, un principio: si una cifra no se puede reproducir, no entra.

| Entregable | Script | Salida |
| --- | --- | --- |
| E5 · catálogo | `data/ref/build_catalog.py` | `policy/catalog.yaml` + `data/mock/credit_product_catalog.csv` |
| E6 · tasas | `data/ref/ingest_regulator_rates.py` | `data/ref/regulator_rates_<fecha>.csv` |

`bundles.yml` los copia al volumen `hackathon.ref.fuentes` y el pipeline lee el volumen. Nunca la API en runtime: ADR-12 lo prohíbe y, además, una respuesta citada en octubre tiene que poder reproducirse con la tasa de octubre.

### E5 · de dónde sale cada cifra
| País | Fuente | Por qué |
| --- | --- | --- |
| AR | BCRA, Régimen de Transparencia, últimos 120 días | hay fuente pública con montos, plazos e ingreso mínimo reales; es más defendible que un percentil |
| CO | percentiles de `credit_limit` del dataset, en COP | moneda dominante del país en `products` |
| MX | ídem, en USD | el dataset **no tiene un solo producto en MXN** (ADR-23) |

18 productos: 6 tipos × 3 países. Nueve tienen contraparte en el dataset y nueve son oferta sin cartera, declarada con `product_type_dataset` vacío. Los tres sin contraparte se derivan del préstamo personal del mismo país con un factor explícito (libranza 0,80 del monto y 0,75 de la tasa; bajo monto 0,10 y 1,15; microcrédito 0,05 y 1,30), para no inventar números sueltos.

Las tasas del catálogo son **la oferta**; el techo legal vive en `ref.regulator_rates` y lo aplica el motor aparte. Para AR se usa p10–mediana del BCRA: el p90 (337 %) es la cola del mercado, no una tasa que este banco ofrecería.

### `product_type_dataset`: la columna que evita un fallo silencioso
`gold.customer_products.product_type` trae los valores del origen en español (`Préstamo Personal`, `Tarjeta Crédito`, `Préstamo Hipotecario`) y el catálogo usa su propia taxonomía (`personal_loan`, `credit_card`, …). `engine.py` compara los dos. Sin una columna puente, `evaluate_eligibility` **no encuentra el producto del cliente y devuelve cero sin error**: el mismo patrón que `country_code` (PR #27) y que `multiLine` (ADR-23).

Se añade la columna en vez de renombrar: los `product_code` y el corpus de ia-ml quedan intactos.

### E6 · estado de las tres fuentes
| Fuente | Estado | Nota |
| --- | --- | --- |
| BCRA (AR) | **automático** | API pública sin auth; 1.018 préstamos personales, 285 hipotecarios y 482 tarjetas informados en los últimos 120 días |
| SFC (CO) | manual | la certificación de usura es un PDF mensual |
| Banxico (MX) | manual | el cuadro CF303 se exporta tras una consulta interactiva |

Las seis filas de CO y MX entran con `source = PENDIENTE` y su URL ya puesta. Un check de DQ **falla mientras quede alguna**: la deuda queda en `ops.dq_results`, no en la cabeza de nadie.

Dos cuidados que el dato exigió:
- **Frescura.** Las entidades informan en fechas que van de 2019 a hoy. Un snapshot ingenuo mezclaría tasas de hace siete años con las de ayer; solo entra lo informado en 120 días.
- **Atípicos.** El régimen publica algún valor absurdo (se vieron TEA de 1.191 % y 1.230 %). Se descarta por encima de 500 % para que no arrastre el percentil 90.

### Correcciones a ADR-12
| Qué | Antes | Ahora |
| --- | --- | --- |
| URL de préstamos personales del BCRA | `.../transparencia/v1.0/prestamosPersonales` → **404** | `.../transparencia/v1.0/Prestamos/Personales` (manual oficial `regimen-transparencia-v1.pdf`) |
| Endpoint de hipotecarios | no estaba | `.../transparencia/v1.0/Prestamos/Hipotecarios`, 293 registros |
| `rate_kind` de AR | se asumía `tna` | es **`ea`**: el BCRA publica tasa efectiva anual, no nominal |

| Alternativas descartadas | Por qué |
| --- | --- |
| Escribir el catálogo a mano | 18 productos × 17 columnas; a la primera corrección las cifras dejan de ser trazables |
| Mantener el mock del catálogo aparte | es como nació la deriva de `rate_kind`; ahora el mock se **genera** del mismo catálogo con las columnas del contrato |
| Renombrar `product_type` del catálogo a los valores del dataset | rompe los `product_code` y el corpus R1–R8 de ia-ml |
| Percentiles del dataset también para AR | el BCRA publica montos, plazos e ingreso mínimo reales; desaprovecharlos sería inventar sobre un dato que existe |
| Dejar MX en MXN | el dataset no tiene MXN: el agente ofrecería un producto en una moneda que el cliente no tiene |
| Consultar las APIs en el pipeline | ADR-12 lo prohíbe y haría irreproducible una respuesta ya citada |
| Esperar a tener CO y MX para entregar E6 | bloquea el pipeline por dos PDF; mejor el check de DQ que falla y la deuda visible |

**Impacto.**

| Elemento | Estado | Owner | Consumers afectados | Qué deben hacer | Fecha límite |
| --- | --- | --- | --- | --- | --- |
| `gold.credit_product_catalog` | cambia: + `product_type_dataset` y `min_score`; 18 productos; MX en USD | datos | **ia-ml** | Manuela: confirmar el cambio de moneda de MX y el uso de `product_type_dataset` en `evaluate_eligibility` | vie 2 |
| `ref.regulator_rates` | cambia: + `rate_kind`; grano a país × producto × rate_kind × snapshot; AR con `ea` y no `tna` | datos | **ia-ml** | Manuela: el techo de AR se lee de la fila `cft`; la de mercado es `ea` | vie 2 |
| `policy.catalog.yaml` | **nuevo**: el catálogo definitivo vive en `policy/`, generado | datos | ia-ml, servicio | Manuela: `settings.catalog_path` ya repunta. Nicolle: `bundles.yml` ya lo copia | hecho |
| `gold.policy_chunks` | existe: **sin cobertura** para `mortgage`, `low_amount_consumer` ni `microcredit` | ia-ml | **datos**, servicio | Manuela: R1–R8 para los tres, o que la matriz los rutee a escalamiento | vie 2 |
| `agent.runtime` (`settings.py`) | cambia: `catalog_path` a `policy/catalog.yaml` | ia-ml | datos | Manuela: aprobar la línea | vie 2 |
| `data/policy_docs/build_corpus.py` | cambia: lee de `policy/`; + `USD` en `CUR_NAME` | ia-ml | datos | Manuela: aprobar; sin `USD` el corpus no compila con MX en dólares | vie 2 |
| `infra.ci_cd` (`bundles.yml`) | cambia: copia `policy/catalog.yaml` y los snapshots de tasas | servicio | datos, ia-ml | Nicolle: aprobar | vie 2 |
| `contracts/gold.yaml` v5 → v6 | cambia: columnas y grano de las dos tablas | datos | ia-ml | Manuela: ninguna acción en código | — |

**Cómo se prueba.**

| Prueba | Umbral | Dónde se registra |
| --- | --- | --- |
| `policy/catalog.yaml` trae las columnas del contrato | 18 productos, 0 columnas faltantes | pytest |
| `product_type_dataset` casa con `gold.customer_products` | 0 valores huérfanos; los 3 productos del dataset con contraparte | pytest + `ops.dq_results` |
| Grano de `ref.regulator_rates` | país × producto × rate_kind único | pytest + `ops.dq_results` |
| `rate_kind` en dominio | 0 fuera de `[ea, tna, cat, cft, usura]` | pytest + `ops.dq_results` |
| Techo por país | CO `usura`, MX `cat`, AR `cft` presentes | pytest + `ops.dq_results` |
| Filas sin fuente real | **falla** mientras `source = PENDIENTE` | `ops.dq_results` |
| Rangos del catálogo | `rate_min ≤ rate_max` y `amount_min ≤ amount_max` | expectativa de SDP + DQ |
| Todo el catálogo es sintético | `es_sintetico = true` en las 18 filas | expectativa de SDP |

**Hackathon vs To-Be.**

| Hackathon | To-Be |
| --- | --- |
| AR por API; CO y MX a mano | las tres por API o scraping versionado con alerta de publicación |
| Snapshot mensual copiado al volumen | tabla con historial y vigencia por fila |
| Catálogo sintético generado de percentiles | catálogo real del banco con vigencia y aprobación de producto |
| `product_type_dataset` como columna puente | taxonomía única de producto en todo el dominio |
| Deuda visible en `ops.dq_results` | bloqueo de despliegue si falta una fuente |

**Dependencias.**

| # | Entregable | De → para | Formato | Fecha | Mock |
| --- | --- | --- | --- | --- | --- |
| E5 (cierra) | catálogo sintético 3×6 generado, con `product_type_dataset` | Eladio → Manuela | `policy/catalog.yaml` + `gold.credit_product_catalog` | hecho jue 2 | el mock se genera del mismo catálogo |
| E6 (parcial) | `ref.regulator_rates` con AR real; CO y MX pendientes de transcribir | Eladio → Manuela | `data/ref/regulator_rates_<fecha>.csv` + Delta | AR hecho jue 2; CO y MX vie 2 | filas `PENDIENTE` con DQ en rojo |
| M10 (nueva) | R1–R8 para `mortgage`, `low_amount_consumer` y `microcredit`, o ruteo a escalamiento | Manuela → Eladio | `data/policy_docs/` | vie 2 | `search_policy` devuelve cero |

**Base regulatoria.** Las tres fuentes son publicaciones oficiales de acceso público: BCRA (Com. A 5460 exige informar CFT), SFC Colombia (Ley 1328/2009, tasa de usura) y Banxico/CONDUSEF (CAT como disclosure obligatoria). Ninguna se consulta en vivo y ninguna es feature, label ni caso de evaluación, según la regla acordada con Factored (ADR-21 §4). El catálogo es sintético y va marcado `es_sintetico = true` en las 18 filas. A validar con legal.
