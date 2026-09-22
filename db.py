from __future__ import annotations

import json
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
        # Academic campus
        "modules": [],
        "forumPosts": [],
        "assessments": [],
        "assessmentAttempts": [],
        "surveys": [],
        "surveyResponses": [],
        "gradeItems": [],
        "grades": [],
        "submissions": [],
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


def canonical_role(role: str | None) -> str:
    """Old coordinator accounts are treated as teachers without breaking old JSON."""
    if role == "coordinator":
        return "teacher"
    return role or "participant"


def safe_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": user.get("id"),
        "name": user.get("name", ""),
        "lastName": user.get("lastName", ""),
        "email": user.get("email", ""),
        "role": canonical_role(user.get("role")),
        "status": user.get("status", "active"),
        "createdAt": user.get("createdAt"),
    }


def ensure_academic_seed(db: dict[str, Any], admin_id: str | None = None) -> bool:
    """Add academic structures to old databases without removing any existing information."""
    changed = False
    if not db["modules"]:
        for number in range(1, 7):
            start_week = (number - 1) * 2 + 1
            end_week = start_week + 1
            db["modules"].append(
                {
                    "id": new_id(),
                    "number": number,
                    "title": f"Módulo {number}",
                    "subtitle": f"Semanas {start_week} y {end_week}",
                    "description": "Unidad formativa de +Q1LÍDER. Personaliza aquí objetivos, contenidos y actividades.",
                    "startWeek": start_week,
                    "endWeek": end_week,
                    "status": "published",
                    "createdBy": admin_id,
                    "createdAt": now_iso(),
                    "updatedAt": now_iso(),
                }
            )
        changed = True

    # Every module gets one default satisfaction survey. It is the gate for the final exam.
    for module in db["modules"]:
        if not any(s.get("moduleId") == module.get("id") for s in db["surveys"]):
            db["surveys"].append(
                {
                    "id": new_id(),
                    "moduleId": module["id"],
                    "title": f"Encuesta de cierre · {module['title']}",
                    "description": "Completa esta encuesta para desbloquear el examen final del módulo.",
                    "questions": [
                        {"id": new_id(), "text": "¿Qué tan útil te resultó el módulo?", "type": "rating"},
                        {"id": new_id(), "text": "¿Qué fue lo más valioso que aprendiste?", "type": "text"},
                        {"id": new_id(), "text": "¿Qué mejorarías del módulo?", "type": "text"},
                    ],
                    "createdBy": admin_id,
                    "createdAt": now_iso(),
                }
            )
            changed = True
    return changed


def ensure_seed() -> None:
    db = read_db()
    changed = False
    fresh_install = not bool(db["users"])

    if not db["users"]:
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
        teacher_id = new_id()
        db["users"].append(
            {
                "id": teacher_id,
                "name": "Docente",
                "lastName": "Demo",
                "email": "docente@q1lider.local",
                "passwordHash": hash_password("Docente2026!"),
                "role": "teacher",
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
                "message": "Tu campus +Q1LÍDER está listo para navegar.",
                "read": False,
                "createdAt": now_iso(),
            }
        )
        db["announcements"].append(
            {
                "id": new_id(),
                "title": "Plataforma lista",
                "message": "Ya puedes organizar actividades, módulos, materiales, asistencia, exámenes y calificaciones.",
                "createdAt": now_iso(),
            }
        )
        changed = True
    else:
        admin_id = next((u.get("id") for u in db["users"] if canonical_role(u.get("role")) == "admin"), None)

    # Normalize old coordinator accounts to teacher for the new administration UI.
    for user in db["users"]:
        if user.get("role") == "coordinator":
            user["role"] = "teacher"
            user["updatedAt"] = now_iso()
            changed = True

    if ensure_academic_seed(db, admin_id):
        changed = True

    # Demonstration academic content only on a brand-new installation.
    if fresh_install and db["modules"] and not db["assessments"]:
        module1 = sorted(db["modules"], key=lambda m: int(m.get("number") or 0))[0]
        case_item = {
            "id": new_id(), "moduleId": module1["id"], "title": "Caso práctico", "type": "case", "weight": 30,
            "createdBy": admin_id, "createdAt": now_iso(), "updatedAt": now_iso(),
        }
        auto_item = {
            "id": new_id(), "moduleId": module1["id"], "title": "Autoevaluación 1", "type": "self_assessment", "weight": 20,
            "createdBy": admin_id, "createdAt": now_iso(), "updatedAt": now_iso(),
        }
        final_item = {
            "id": new_id(), "moduleId": module1["id"], "title": "Examen final", "type": "final_exam", "weight": 50,
            "createdBy": admin_id, "createdAt": now_iso(), "updatedAt": now_iso(),
        }
        db["gradeItems"].extend([case_item, auto_item, final_item])
        demo_questions = [
            {"id": new_id(), "text": "¿Cuál es una característica esencial del liderazgo efectivo?", "options": ["Escucha activa", "Evitar delegar", "Trabajar sin objetivos"], "correctIndex": 0},
            {"id": new_id(), "text": "¿Qué ayuda a organizar mejor un proyecto?", "options": ["No definir responsables", "Definir objetivos y seguimiento", "Cambiar metas diariamente"], "correctIndex": 1},
        ]
        db["assessments"].append({
            "id": new_id(), "moduleId": module1["id"], "title": "Autoevaluación 1", "description": "Autoevaluación de demostración del primer módulo.",
            "type": "self_assessment", "questions": deepcopy(demo_questions), "gradeItemId": auto_item["id"],
            "createdBy": admin_id, "createdAt": now_iso(), "updatedAt": now_iso(),
        })
        db["assessments"].append({
            "id": new_id(), "moduleId": module1["id"], "title": "Examen final · Módulo 1", "description": "Se desbloquea después de contestar la encuesta del módulo.",
            "type": "final_exam", "questions": deepcopy(demo_questions), "gradeItemId": final_item["id"],
            "createdBy": admin_id, "createdAt": now_iso(), "updatedAt": now_iso(),
        })
        for ctype, name, description in [
            ("module_plan", "Plan del Módulo 1", "Estructura y objetivos generales del módulo."),
            ("study_guide", "Guía de estudio complementaria", "Material guía para reforzar los temas principales."),
            ("case_statement", "Enunciado del caso práctico", "Caso de demostración listo para sustituirse por el contenido real."),
            ("project_practical", "Enunciado práctico para proyecto", "Indicaciones de demostración para el proyecto del módulo."),
            ("master_class", "Master class de demostración", "Espacio preparado para cargar o enlazar la clase grabada."),
        ]:
            db["materials"].append({
                "id": new_id(), "name": name, "description": description, "category": "Capacitaciones",
                "contentType": ctype, "moduleId": module1["id"], "authorId": admin_id, "fileName": None,
                "originalName": None, "mime": None, "url": None, "createdAt": now_iso(), "updatedAt": now_iso(),
            })
        changed = True

    if changed:
        write_db(db)
    else:
        # normalize adds missing collections in memory; persist them for old databases
        write_db(db)


def reset_local_data() -> None:
    if DB_FILE.exists():
        DB_FILE.unlink()
    if UPLOAD_DIR.exists():
        for item in UPLOAD_DIR.iterdir():
            if item.is_file() and item.name != ".gitkeep":
                item.unlink()
    ensure_seed()
