"""Importa los datos locales de la versión React/Express a la versión Flask.

Uso:
    python migrate_node_data.py "D:\\q1lider-simple"

La carpeta indicada debe contener server/data/db.json y, opcionalmente, server/uploads/.
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

from db import DB_FILE, UPLOAD_DIR, ensure_seed, normalize, write_db


def main() -> int:
    if len(sys.argv) < 2:
        print('Uso: python migrate_node_data.py "D:\\ruta\\q1lider-simple"')
        return 1
    source = Path(sys.argv[1]).expanduser().resolve()
    source_db = source / "server" / "data" / "db.json"
    source_uploads = source / "server" / "uploads"
    if not source_db.exists():
        print(f"❌ No encontré {source_db}")
        return 2
    try:
        data = normalize(json.loads(source_db.read_text(encoding="utf-8")))
    except Exception as exc:
        print(f"❌ No pude leer el JSON: {exc}")
        return 3
    if DB_FILE.exists():
        backup = DB_FILE.with_name(f"db-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json")
        shutil.copy2(DB_FILE, backup)
        print(f"📦 Backup creado: {backup}")
    write_db(data)
    ensure_seed()  # agrega módulos/encuestas académicas sin borrar lo migrado
    copied = 0
    if source_uploads.exists():
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        for item in source_uploads.iterdir():
            if item.is_file():
                shutil.copy2(item, UPLOAD_DIR / item.name)
                copied += 1
    print(f"✅ Datos migrados: {len(data['users'])} usuarios, {len(data['events'])} actividades, {len(data['materials'])} materiales y {copied} archivos.")
    print("Ya puedes ejecutar: python app.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
