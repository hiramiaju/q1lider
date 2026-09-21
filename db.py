from __future__ import annotations

import json
import os
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

import bcrypt

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_FILE = DATA_DIR / "db.json"
UPLOAD_DIR = BASE_DIR / "uploads"
LOCK = RLock()


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def new_id() -> str:
    return str(uuid4())


def base_db() -> dict[str, Any]:
    return {
        "users": [],
        "events": [],
        "tasks": [],
        "materials": [],
        "notes": [],
        "notifications": [],
        "announcements": [],
        "categories": [],
        "attendanceSessions": [],
        "attendanceRecords": [],
        "materialComments": [],
    }


def normalize(db: dict[str, Any] | None) -> dict[str, Any]:
    db = db or {}
    base = base_db()
    for key in base:
        if not isinstance(db.get(key), list):
            db[key] = []
    return db


def read_db() -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    with LOCK:
        if not DB_FILE.exists():
            DB_FILE.write_text(json.dumps(base_db(), indent=2, ensure_ascii=False), encoding="utf-8")
        try:
            return normalize(json.loads(DB_FILE.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            backup = DB_FILE.with_suffix(".corrupt.json")
            try:
                DB_FILE.replace(backup)
            except OSError:
                pass
            fresh = base_db()
            write_db(fresh)
            return fresh


def write_db(db: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with LOCK:
        normalized = normalize(deepcopy(db))
        temp = DB_FILE.with_suffix(".tmp")
        temp.write_text(json.dumps(normalized, indent=2, ensure_ascii=False), encoding="utf-8")
        temp.replace(DB_FILE)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=10)).decode("utf-8")


def check_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def safe_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": user.get("id"),
        "name": user.get("name", ""),
        "lastName": user.get("lastName", ""),
        "email": user.get("email", ""),
        "role": user.get("role", "participant"),
        "status": user.get("status", "active"),
    }


def ensure_seed() -> None:
    db = read_db()
    if db["users"]:
        # This keeps old JSON files from the Node version compatible.
        write_db(db)
        return

    admin_id = new_id()
    db["users"].append(
        {
            "id": admin_id,
            "name": "Administrador",
            "lastName": "+Q1LÍDER",
            "email": "admin@q1lider.local",
            "passwordHash": hash_password("Q1Lider2026!"),
            "role": "admin",
            "status": "active",
            "createdAt": now_iso(),
            "updatedAt": now_iso(),
        }
    )

    for name, last_name, email in [
        ("Ana", "Martínez", "ana@q1lider.local"),
        ("Diego", "López", "diego@q1lider.local"),
        ("Sofía", "Ramírez", "sofia@q1lider.local"),
    ]:
        db["users"].append(
            {
                "id": new_id(),
                "name": name,
                "lastName": last_name,
                "email": email,
                "passwordHash": hash_password("Demo2026!"),
                "role": "participant",
                "status": "active",
                "createdAt": now_iso(),
                "updatedAt": now_iso(),
            }
        )

    today = datetime.now().date()
    demo_events = [
        ("Taller de Liderazgo", 2, "09:00", "11:00", "Auditorio"),
        ("Reunión de Coordinadores", 5, "16:00", "17:30", "Sala de juntas"),
        ("Actividad Comunitaria", 9, "08:00", "13:00", "Casa Blanca"),
        ("Capacitación +Q1LÍDER", 13, "10:00", "12:00", "Sala de capacitación"),
        ("Entrega de Proyecto", 18, "18:00", "19:00", "En línea"),
    ]
    for title, offset, start, end, place in demo_events:
        db["events"].append(
            {
                "id": new_id(),
                "title": title,
                "description": "Actividad de demostración +Q1LÍDER",
                "date": (today + timedelta(days=offset)).isoformat(),
                "startTime": start,
                "endTime": end,
                "place": place,
                "type": "official",
                "status": "pending",
                "priority": "medium",
                "ownerId": admin_id,
                "responsibleId": admin_id,
                "participants": [],
                "checklist": [],
                "createdAt": now_iso(),
                "updatedAt": now_iso(),
            }
        )

    db["tasks"].append(
        {
            "id": new_id(),
            "title": "Revisar material del taller",
            "description": "Tarea demo",
            "dueDate": (today + timedelta(days=1)).isoformat(),
            "priority": "high",
            "status": "pending",
            "ownerId": admin_id,
            "personal": True,
            "checklist": [],
            "createdAt": now_iso(),
            "updatedAt": now_iso(),
        }
    )
    db["notifications"].append(
        {
            "id": new_id(),
            "userId": admin_id,
            "title": "Bienvenido a +Q1LÍDER",
            "message": "Tu plataforma Flask está lista para navegar.",
            "read": False,
            "createdAt": now_iso(),
        }
    )
    db["announcements"].append(
        {
            "id": new_id(),
            "title": "Plataforma lista",
            "message": "Ya puedes organizar actividades, tareas, materiales y asistencia desde un solo lugar.",
            "createdAt": now_iso(),
        }
    )
    write_db(db)


def reset_local_data() -> None:
    if DB_FILE.exists():
        DB_FILE.unlink()
    if UPLOAD_DIR.exists():
        for item in UPLOAD_DIR.iterdir():
            if item.is_file():
                item.unlink()
    ensure_seed()
