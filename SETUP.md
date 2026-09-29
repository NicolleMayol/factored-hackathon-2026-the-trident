# Cómo subir esto al repo y cómo usa el skill cada persona

## 1. Manuela: primer commit (10 min)
```bash
git clone git@github.com:<org>/factored-hackathon-2026-<equipo>.git
cd factored-hackathon-2026-<equipo>
# copiar el contenido de repo-bundle/ en la raíz (incluye carpetas ocultas .claude y .github)
cp -r /ruta/repo-bundle/. .
# reemplazar handles de GitHub en 3 archivos
sed -i '' 's/@MANUELA_GH/@tu-usuario/g; s/@ELADIO_GH/@usuario-eladio/g; s/@NICOLLE_GH/@usuario-nicolle/g' .github/CODEOWNERS .github/pull_request_template.md contracts/impact-map.yaml
git checkout -b docs/adr-bootstrap
git add -A && git commit -m "docs(adr): bootstrap ADR, contratos, skill adr-hackathon y gate de impacto"
git push -u origin docs/adr-bootstrap
```
Abre el PR; Nicolle lo mergea. Luego en GitHub → Settings → Branches → rule para `main`: "Require pull request", "Require review from Code Owners", "Require status checks: adr-impact". Con eso el gate es real: nadie mergea un cambio de contrato sin el approve de los roles afectados.

## 2. Qué hay en el bundle
| Ruta | Qué es | Quién lo toca |
| --- | --- | --- |
| .claude/skills/adr-hackathon/SKILL.md | el skill (preguntas por rol, gate de impacto, plantilla) | todos lo usan; Manuela lo mantiene |
| contracts/impact-map.yaml | quién posee y quién consume cada elemento; alimenta el gate | quien cree un elemento nuevo |
| contracts/*.yaml, handoff.schema.json | contratos gold, tools, api, chunks, ops, infra | cada owner, por PR |
| policy/*.yaml | matriz de política, glosario (catalog.yaml lo genera Eladio en E5) | Manuela; Eladio el catálogo |
| docs/adr/*.md | ADR por secciones; 08-datos y 09-servicio están PENDIENTES para Eladio y Nicolle | el owner de cada sección |
| .github/CODEOWNERS | revisores obligatorios por carpeta | Nicolle |
| .github/pull_request_template.md | obliga a declarar rol, tipo, impacto y aviso | todos |
| .github/workflows/adr-impact.yml + scripts/impact_check.py | comenta el impacto en cada PR y bloquea si falta el aviso | Nicolle |
| AGENTS.md, .github/copilot-instructions.md | para que Copilot, Codex u otro agente sigan el mismo skill | — |

## 3. Cómo usa el skill cada persona
| Herramienta | Qué hacer |
| --- | --- |
| Claude Code (terminal) | `git pull`; el skill se detecta solo desde `.claude/skills/`. Escribir: "documentar mi parte" o "/adr-hackathon". |
| Claude.ai / Cowork / Desktop | Subir la carpeta `adr-hackathon` (con SKILL.md) en Configuración → Skills, o abrir el repo como carpeta conectada. |
| GitHub Copilot (VS Code) | Nada extra: `.github/copilot-instructions.md` le indica seguir SKILL.md. Pedir "documenta mi decisión siguiendo el skill adr-hackathon". |
| Codex / otros agentes | Leen `AGENTS.md`. |

Ejemplo (Nicolle): "Voy a cambiar el plan de la Function a Premium y renombrar SQL_HTTP_PATH a DBX_SQL_PATH". El skill pregunta recurso, secretos, contrato de API, resiliencia, observabilidad, CI, capacidad; lee impact-map; detecta que `infra.function_app_settings` lo consume ia-ml; se detiene y muestra: "@Manuela · ia-ml: cambia el nombre del App Setting SQL_HTTP_PATH → DBX_SQL_PATH · debes actualizar agent/config.py · antes del mié 30 · si no, el caso normal no conecta a gold". Solo después genera el apartado y el PR. El workflow `adr-impact` repite el chequeo en GitHub y bloquea el merge hasta el approve de Manuela.

## 4. Un skill o varios
Uno basta para el comportamiento humano (documentar + detectar impacto), porque el impacto es un paso del mismo flujo y comparte el mapa. Lo que no puede hacer un skill es vigilar el repo cuando nadie está preguntando: eso lo hace el workflow `adr-impact` + CODEOWNERS. Son dos piezas, no dos skills: el skill avisa antes de escribir; el workflow impide mergear sin el approve.
