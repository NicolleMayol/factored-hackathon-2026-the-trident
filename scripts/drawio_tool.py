"""Herramientas draw.io para doc-as-code.
  python scripts/drawio_tool.py styles diagrams/arquitectura.drawio  -> diagrams/styles.yaml (catálogo de iconos/estilos reutilizables)
  python scripts/drawio_tool.py sync   diagrams/arquitectura.drawio  -> compara atributos element= de las celdas con contracts/impact-map.yaml; exit 2 si hay desalineación
  python scripts/drawio_tool.py decompress in.drawio out.drawio      -> deja el XML sin comprimir (obligatorio para diffs y para que la IA lo edite)
"""
import sys, re, zlib, base64, html, json
import xml.etree.ElementTree as ET
try:
    import yaml
except ImportError:
    yaml = None

def load(path):
    tree = ET.parse(path); root = tree.getroot()
    for d in root.iter("diagram"):
        if len(d) == 0 and (d.text or "").strip():  # comprimido
            raw = base64.b64decode(d.text.strip())
            xml = html.unescape(__import__("urllib.parse").parse.unquote(zlib.decompress(raw, -15).decode()))
            d.text = None; d.append(ET.fromstring(xml))
    return tree

def styles(path, out="diagrams/styles.yaml"):
    """Catálogo: icono (image= o shape=mxgraph) + etiqueta más cercana (misma capa, debajo o al lado)."""
    import hashlib
    tree = load(path); cat = {}
    def clean(v): return re.sub(r"<[^>]+>", " ", v or "").replace("&nbsp;", " ").strip()
    def geo(c):
        g = c.find("mxGeometry"); return [float(g.get(k) or 0) for k in ("x", "y", "width", "height")]
    for page in tree.iter("diagram"):
        cs = [c for c in page.iter("mxCell") if c.get("vertex") == "1"]
        icons = [c for c in cs if "image=" in c.get("style", "") or "shape=mxgraph" in c.get("style", "")]
        texts = [c for c in cs if clean(c.get("value")) and "image=" not in c.get("style", "")]
        for ic in icons:
            x, y, w, h = geo(ic); label = clean(ic.get("value"))
            if not label:
                best, bd = None, 1e9
                for tx in texts:
                    if tx.get("parent") != ic.get("parent"): continue
                    tx_, ty, tw, th = geo(tx); d = abs((x + w/2) - (tx_ + tw/2)) + max(0, ty - (y + h)) * 0.5
                    if y - 5 <= ty < y + h + 60 and abs((x + w/2) - (tx_ + tw/2)) < w + 40 and d < bd: bd, best = d, tx
                label = clean(best.get("value")) if best is not None else "sin-etiqueta"
            st = ic.get("style", ""); key = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")[:40] or "sin-etiqueta"
            if "image=data:" in st: key += "-" + hashlib.md5(st.encode()).hexdigest()[:6]
            cat.setdefault(key, {"label": label, "page": page.get("name"), "style": st, "w": round(w, 1), "h": round(h, 1)})
    text = yaml.safe_dump(cat, allow_unicode=True, sort_keys=True, width=10000) if yaml else json.dumps(cat, ensure_ascii=False, indent=2)
    open(out, "w").write("# Catálogo de iconos/estilos extraído de diagrams/arquitectura.drawio. Reutilizar tal cual (style, w, h).\n" + text)
    print(f"{len(cat)} estilos -> {out}")

def sync(path, impact="contracts/impact-map.yaml"):
    tree = load(path); in_diagram = {}
    for obj in tree.iter("object"):
        el = obj.get("element")
        if el: in_diagram.setdefault(el, []).append((obj.get("label") or "", obj.get("adr") or ""))
    ids = {e["id"] for e in yaml.safe_load(open(impact))["elements"]} if yaml else set()
    missing_in_map = sorted(set(in_diagram) - ids)
    missing_in_diagram = sorted(ids - set(in_diagram))
    print("Elementos en el diagrama sin entrada en impact-map:", missing_in_map or "ninguno")
    print("Elementos del impact-map sin dibujar (revisar si aplica):", missing_in_diagram or "ninguno")
    untagged = sum(1 for c in tree.iter("mxCell") if c.get("vertex") == "1" and c.get("style", "").find("shape=mxgraph") >= 0)
    print(f"Celdas con icono: {untagged}; con element= : {len(in_diagram)}")
    if missing_in_map: sys.exit(2)

def decompress(src, dst):
    tree = load(src); tree.write(dst, encoding="utf-8", xml_declaration=True); print("ok ->", dst)

if __name__ == "__main__":
    cmd = sys.argv[1]
    {"styles": lambda: styles(sys.argv[2]), "sync": lambda: sync(sys.argv[2]), "decompress": lambda: decompress(sys.argv[2], sys.argv[3])}[cmd]()
