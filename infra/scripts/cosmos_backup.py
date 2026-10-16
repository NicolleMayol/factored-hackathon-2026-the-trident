"""Respaldo y restauración de los contenedores de Cosmos (workflow shutdown).

  python infra/scripts/cosmos_backup.py backup  <dir>            # un <contenedor>.jsonl por contenedor
  python infra/scripts/cosmos_backup.py restore <dir> [nombres]  # upsert desde los .jsonl

Lee COSMOS_ENDPOINT y COSMOS_KEY del entorno. Respaldar no cambia nada en la cuenta; restaurar hace
upsert, así que repetirlo no duplica documentos.
"""
import json
import os
import sys
from pathlib import Path

from azure.cosmos import CosmosClient

DATABASE = "agent"
CONTAINERS = ["conversations", "handoffs", "policy_chunks"]
SYSTEM_FIELDS = ("_rid", "_self", "_etag", "_attachments", "_ts")


def backup(db, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    existing = {c["id"] for c in db.list_containers()}
    for name in CONTAINERS:
        if name not in existing:
            print(f"{name}: no existe, se omite")
            continue
        n = 0
        with open(out / f"{name}.jsonl", "w", encoding="utf-8") as f:
            for doc in db.get_container_client(name).read_all_items():
                f.write(json.dumps(doc, ensure_ascii=False) + "\n")
                n += 1
        print(f"{name}: {n} documentos")


def restore(db, src: Path, names: list[str]) -> None:
    for name in names or CONTAINERS:
        path = src / f"{name}.jsonl"
        if not path.exists():
            print(f"{name}: sin {path.name}, se omite")
            continue
        container = db.get_container_client(name)
        n = 0
        with open(path, encoding="utf-8") as f:
            for line in f:
                doc = json.loads(line)
                for k in SYSTEM_FIELDS:
                    doc.pop(k, None)
                container.upsert_item(doc)
                n += 1
        print(f"{name}: {n} documentos restaurados")


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in ("backup", "restore"):
        sys.exit(__doc__)
    db = CosmosClient(os.environ["COSMOS_ENDPOINT"], os.environ["COSMOS_KEY"]).get_database_client(DATABASE)
    if sys.argv[1] == "backup":
        backup(db, Path(sys.argv[2]))
    else:
        restore(db, Path(sys.argv[2]), sys.argv[3:])
