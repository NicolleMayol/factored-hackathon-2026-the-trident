# 12-fuentes-externas

Owner: Eladio · v2 · 2026-10-01 (sección "Justificación por fuente" añadida por ia-ml, ADR-21; Eladio completa fecha de snapshot y licencia al registrar E6).

Ninguna fuente se consulta en vivo. Entran por batch versionado: ref.regulator_rates (SFC CO, Banxico/CONDUSEF MX, BCRA AR, BACEN opcional), textos normativos públicos como base de policy_docs (Ley 1328/2009, LFPDPPP, Ley 24.240 + Com. A 5460, CDC), daily_exchange_rates del dataset, glosario. Prohibido: burós, datos de bancos reales, APIs externas en runtime, PII.

## Regla acordada con Factored (2026-10-01)

Factored autorizó el uso de fuentes externas junto al dataset con dos condiciones: justificar explícitamente cada fuente y no usarlas para testing. Aquí, "testing" se cumple así: ninguna fuente externa es feature, label ni caso de evaluación; todas las métricas de modelo se calculan sobre el dataset de Factored y el eval del agente usa solo los clientes de prueba y el catálogo sintético (`docs/adr/06-evaluacion.md`). Las fuentes externas son únicamente contexto del RAG y techo del motor de reglas, y un test en CI lo verifica.

## Justificación por fuente

| Fuente | URL | Qué aporta que el dataset no tiene | Dónde se usa | Formato / frescura | `es_sintetico` |
| --- | --- | --- | --- | --- | --- |
| BCRA · Régimen de Transparencia, préstamos personales | https://api.bcra.gob.ar/transparencia/v1.0/prestamosPersonales | TNA, TEA y CFT reales de mercado por entidad; sin esto el agente no puede dar un rango de referencia ni verificar que una cifra es plausible (Com. A 5460 exige informar CFT) | `ref.regulator_rates` (AR); Verify; redacción de requisitos en `policy_docs` | JSON, API pública sin auth; snapshot mensual | false |
| BCRA · Régimen de Transparencia, tarjetas de crédito | https://api.bcra.gob.ar/transparencia/v1.0/tarjetasCredito | Igual, para tarjetas | `ref.regulator_rates` (AR) | JSON; snapshot mensual | false |
| Superintendencia Financiera de Colombia · certificación de interés bancario corriente | https://www.superfinanciera.gov.co/publicaciones/10116142/superfinanciera-certifica-el-interes-bancario-corriente/ | Tasa de usura por modalidad: el techo legal que ninguna respuesta puede superar (Ley 1328/2009) | `ref.regulator_rates` (CO); Verify; `catalog.yaml` | PDF mensual, transcrito a 5–7 filas | false |
| Banxico · SIE cuadro CF303 | https://www.banxico.org.mx/SieInternet/consultarDirectorioInternetAction.do?sector=18&accion=consultarCuadro&idCuadro=CF303&locale=es | Tasa mínima, máxima, promedio y CAT por producto: el CAT es disclosure obligatoria (CONDUSEF) | `ref.regulator_rates` (MX); Verify; sección R3 de `policy_docs` | CSV exportable; snapshot mensual | false |
| Ley 1328/2009 (CO) | https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=36841 | Base del deber de información clara y de tasa y costo total | citada en `source` de los chunks R3 (CO) | texto; no se carga en tabla | — |
| Ley 1581/2012 (CO) | https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=49981 | Base de consentimiento y uso de datos | `source` de chunks R6 (CO) | texto | — |
| LFPDPPP (MX) | https://www.diputados.gob.mx/LeyesBiblio/pdf/LFPDPPP.pdf | Base del aviso de privacidad | `source` de chunks R6 (MX) | PDF | — |
| Com. A 5460 BCRA (AR) | https://www.bcra.gob.ar/archivos/Pdfs/texord/t-ri-transpa.pdf | Base de la disclosure TNA/TEA/CFT y de atención de reclamos | `source` de chunks R3 y R7 (AR) | PDF | — |
| Ley 25.326 (AR) | https://servicios.infoleg.gob.ar/infolegInternet/anexos/60000-64999/64790/norma.htm | Base de consentimiento | `source` de chunks R6 (AR) | texto | — |
| `gold.credit_product_catalog` | sintético (E5) | Productos plausibles por país cruzando percentiles del dataset con rangos regulatorios | motor de reglas, RAG, eval | Delta + `policy/catalog.yaml` | **true** |

Lo que no entra: burós de crédito, páginas de productos de bancos reales identificables, comparadores comerciales, consultas externas en tiempo de conversación, PII. Brasil solo si el portugués recibe jurisdicción (BCB Olinda), decisión abierta.

Para ampliar este apartado usa el skill `adr-hackathon` (modo documentar).
