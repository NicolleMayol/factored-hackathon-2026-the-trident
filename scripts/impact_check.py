"""Calcula los roles impactados por los archivos cambiados en un PR y escribe un resumen.
Uso: python scripts/impact_check.py <archivo_con_lista_de_paths> [--author-role datos|ia-ml|servicio]
Salida: impact.md (comentario del PR) y exit 2 si hay impacto cruzado sin aviso en el cuerpo del PR.
"""
import sys, os, re, json
import yaml  # pip install pyyaml

def main():
    changed = [l.strip() for l in open(sys.argv[1]) if l.strip()]
    author_role = None
    if "--author-role" in sys.argv:
        author_role = sys.argv[sys.argv.index("--author-role") + 1]
    m = yaml.safe_load(open("contracts/impact-map.yaml"))
    roles = m["roles"]
    hits = []
    for el in m["elements"]:
        if any(c == el["file"] or c.startswith(el["file"].rstrip("*")) for c in changed):
            hits.append(el)
    impacted = {}
    for el in hits:
        for r in el.get("consumers", []):
            if r != author_role:
                impacted.setdefault(r, []).append(el)
    lines = ["## Impacto cruzado detectado por `adr-impact`", ""]
    if not hits:
        lines.append("Ningún elemento del mapa de impacto cambió. Sin revisión cruzada obligatoria.")
    else:
        lines.append("| Elemento | Archivo | Owner | Consumers | Usado por |")
        lines.append("| --- | --- | --- | --- | --- |")
        for el in hits:
            lines.append(f"| `{el['id']}` | `{el['file']}` | {roles[el['owner']]['name']} | "
                         f"{', '.join(roles[r]['name'] for r in el.get('consumers', []))} | "
                         f"{', '.join(map(str, el.get('used_by', [])))} |")
        lines.append("")
        if impacted:
            lines.append("**Antes de seguir, deben aprobar:** " +
                         ", ".join(f"{roles[r]['github']} ({roles[r]['name']})" for r in impacted))
        else:
            lines.append("El cambio solo afecta elementos que consume el mismo autor.")
    open("impact.md", "w").write("\n".join(lines))
    body = os.environ.get("PR_BODY", "")
    missing = [r for r in impacted if roles[r]["github"].lower() not in body.lower()]  # los @handles de GitHub no distinguen mayúsculas
    if missing:
        print("Falta aviso en el PR a:", ", ".join(roles[r]["name"] for r in missing))
        sys.exit(2)

if __name__ == "__main__":
    main()
