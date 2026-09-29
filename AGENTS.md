# Guía para agentes de IA en este repo
- Documentación y contratos: sigue `.claude/skills/adr-hackathon/SKILL.md` antes de escribir en `docs/adr/`, `contracts/` o `policy/`.
- Impacto cruzado: consulta `contracts/impact-map.yaml`; si tu cambio toca un elemento con consumers distintos a tu rol, detente, genera la tabla de impacto y el aviso, y no continúes con la implementación hasta que esté en el PR.
- Solo Nicolle mergea a main. PR por apartado. Título `adr(<rol>): <título>`.
