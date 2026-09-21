from __future__ import annotations

import os
from calendar import monthrange
from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path
from typing import Any, Callable

from flask import (
    Flask,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from werkzeug.utils import secure_filename

from db import (
    UPLOAD_DIR,
    check_password,
    ensure_seed,
    hash_password,
    new_id,
    now_iso,
    read_db,
    safe_user,
    write_db,
)

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("Q1LIDER_SECRET", "q1lider-flask-local-secret-change-in-production"),
    MAX_CONTENT_LENGTH=25 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

ALLOWED_EXTENSIONS = {
    "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "png", "jpg", "jpeg", "gif", "webp",
    "mp4", "webm", "mov", "mp3", "wav", "m4a", "txt", "csv", "zip"
}
ROLES = {"admin", "coordinator", "participant"}
ATTENDANCE_STATUSES = {"present", "absent", "late", "excused"}


def current_user() -> dict[str, Any] | None:
    uid = session.get("user_id")
    if not uid:
        return None
    db = read_db()
    user = next((u for u in db["users"] if u.get("id") == uid and u.get("status") == "active"), None)
    if not user:
        session.clear()
        return None
    return user


@app.before_request
def load_user() -> None:
    g.user = current_user()


@app.context_processor
def inject_globals() -> dict[str, Any]:
    unread = 0
    if g.get("user"):
        db = read_db()
        unread = sum(1 for n in db["notifications"] if n.get("userId") == g.user["id"] and not n.get("read"))
    return {
        "current_user": safe_user(g.user) if g.get("user") else None,
        "unread_notifications": unread,
    }


def login_required(view: Callable) -> Callable:
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not g.get("user"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def roles_required(*roles: str) -> Callable:
    def decorator(view: Callable) -> Callable:
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if g.user.get("role") not in roles:
                flash("No tienes permisos para realizar esa acción.", "error")
                return redirect(url_for("calendar_page"))
            return view(*args, **kwargs)
        return wrapped
    return decorator


def parse_bool(value: Any) -> bool:
    return str(value).lower() in {"1", "true", "yes", "on"}


def author_name(db: dict[str, Any], user_id: str) -> str:
    user = next((u for u in db["users"] if u.get("id") == user_id), None)
    return f"{user.get('name', '')} {user.get('lastName', '')}".strip() if user else "Usuario"


def can_manage_event(event: dict[str, Any], user: dict[str, Any]) -> bool:
    if event.get("type") == "personal":
        return event.get("ownerId") == user.get("id")
    return user.get("role") in {"admin", "coordinator"}


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_uploaded_file(file_storage) -> tuple[str | None, str | None, str | None]:
    if not file_storage or not file_storage.filename:
        return None, None, None
    original = secure_filename(file_storage.filename)
    if not original or not allowed_file(original):
        raise ValueError("Formato de archivo no permitido.")
    stamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    filename = f"{stamp}-{original}"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    file_storage.save(UPLOAD_DIR / filename)
    return filename, original, file_storage.mimetype


@app.errorhandler(413)
def file_too_large(_):
    flash("El archivo supera el límite de 25 MB.", "error")
    return redirect(request.referrer or url_for("material_page"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.get("user"):
        return redirect(url_for("calendar_page"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        db = read_db()
        user = next((u for u in db["users"] if u.get("email", "").lower() == email and u.get("status") == "active"), None)
        if not user or not check_password(password, user.get("passwordHash", "")):
            flash("Correo o contraseña incorrectos.", "error")
        else:
            session.clear()
            session["user_id"] = user["id"]
            return redirect(request.args.get("next") or url_for("calendar_page"))
    return render_template("login.html")


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def calendar_page():
    db = read_db()
    uid = g.user["id"]
    today = date.today()
    try:
        year = int(request.args.get("year", today.year))
        month = int(request.args.get("month", today.month))
        first = date(year, month, 1)
    except (ValueError, TypeError):
        first = date(today.year, today.month, 1)
        year, month = first.year, first.month

    filter_name = request.args.get("filter", "all")
    events = [e for e in db["events"] if e.get("type") == "official" or e.get("ownerId") == uid]
    if filter_name == "official":
        events = [e for e in events if e.get("type") == "official"]
    elif filter_name == "personal":
        events = [e for e in events if e.get("type") == "personal"]
    elif filter_name == "completed":
        events = [e for e in events if e.get("status") == "completed"]
    elif filter_name == "pending":
        events = [e for e in events if e.get("status") != "completed"]

    start = first - timedelta(days=(first.weekday() + 1) % 7)  # Sunday
    days = []
    for i in range(42):
        d = start + timedelta(days=i)
        d_events = sorted([e for e in events if e.get("date") == d.isoformat()], key=lambda x: x.get("startTime", ""))
        days.append({"date": d, "same_month": d.month == month, "events": d_events})

    prev = (first - timedelta(days=1)).replace(day=1)
    next_month = (first.replace(day=monthrange(year, month)[1]) + timedelta(days=1)).replace(day=1)
    announcements = sorted(db["announcements"], key=lambda x: x.get("createdAt", ""), reverse=True)
    mobile_agenda = sorted([e for e in events if e.get("date", "") >= today.isoformat()], key=lambda x: (x.get("date", ""), x.get("startTime", "")))[:30]
    return render_template(
        "calendar.html",
        days=days,
        year=year,
        month=month,
        month_name=["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"][month],
        prev=prev,
        next_month=next_month,
        filter_name=filter_name,
        announcements=announcements,
        mobile_agenda=mobile_agenda,
        today=today,
    )


@app.post("/events")
@login_required
def create_event():
    event_type = "official" if request.form.get("type") == "official" else "personal"
    if event_type == "official" and g.user.get("role") not in {"admin", "coordinator"}:
        abort(403)
    title = request.form.get("title", "").strip()
    event_date = request.form.get("date", "").strip()
    if not title or not event_date:
        flash("Título y fecha son obligatorios.", "error")
        return redirect(request.referrer or url_for("calendar_page"))
    db = read_db()
    item = {
        "id": new_id(),
        "title": title[:180],
        "description": request.form.get("description", "").strip()[:5000],
        "date": event_date,
        "startTime": request.form.get("startTime", "09:00"),
        "endTime": request.form.get("endTime", "10:00"),
        "place": request.form.get("place", "").strip()[:250],
        "type": event_type,
        "status": request.form.get("status", "pending"),
        "priority": request.form.get("priority", "medium"),
        "category": request.form.get("category", ""),
        "ownerId": g.user["id"],
        "responsibleId": g.user["id"],
        "participants": [],
        "checklist": [],
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
    }
    db["events"].append(item)
    write_db(db)
    flash("Actividad creada correctamente.", "success")
    return redirect(request.referrer or url_for("calendar_page"))


@app.post("/events/<event_id>/update")
@login_required
def update_event(event_id: str):
    db = read_db()
    event = next((e for e in db["events"] if e.get("id") == event_id), None)
    if not event:
        abort(404)
    if not can_manage_event(event, g.user):
        abort(403)
    for key in ["title", "description", "date", "startTime", "endTime", "place", "priority", "status", "category"]:
        if key in request.form:
            event[key] = request.form.get(key)
    event["updatedAt"] = now_iso()
    write_db(db)
    flash("Actividad actualizada.", "success")
    return redirect(request.referrer or url_for("calendar_page"))


@app.post("/events/<event_id>/delete")
@login_required
def delete_event(event_id: str):
    db = read_db()
    event = next((e for e in db["events"] if e.get("id") == event_id), None)
    if not event:
        abort(404)
    if not can_manage_event(event, g.user):
        abort(403)
    db["events"] = [e for e in db["events"] if e.get("id") != event_id]
    write_db(db)
    flash("Actividad eliminada.", "success")
    return redirect(url_for("calendar_page"))


@app.route("/tareas")
@login_required
def tasks_page():
    db = read_db()
    uid = g.user["id"]
    tasks = [t for t in db["tasks"] if t.get("ownerId") == uid or t.get("assignedTo") == uid]
    tasks.sort(key=lambda t: (t.get("status") == "completed", t.get("dueDate") or "9999-12-31"))
    return render_template("tasks.html", tasks=tasks)


@app.post("/tasks")
@login_required
def create_task():
    title = request.form.get("title", "").strip()
    if not title:
        flash("El título es obligatorio.", "error")
        return redirect(url_for("tasks_page"))
    db = read_db()
    item = {
        "id": new_id(),
        "title": title[:180],
        "description": request.form.get("description", "").strip()[:5000],
        "dueDate": request.form.get("dueDate") or None,
        "priority": request.form.get("priority", "medium"),
        "status": request.form.get("status", "pending"),
        "ownerId": g.user["id"],
        "personal": True,
        "checklist": [],
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
    }
    db["tasks"].append(item)
    write_db(db)
    flash("Tarea guardada.", "success")
    return redirect(url_for("tasks_page"))


@app.post("/tasks/<task_id>/toggle")
@login_required
def toggle_task(task_id: str):
    db = read_db()
    task = next((t for t in db["tasks"] if t.get("id") == task_id and (t.get("ownerId") == g.user["id"] or t.get("assignedTo") == g.user["id"])), None)
    if not task:
        abort(404)
    task["status"] = "pending" if task.get("status") == "completed" else "completed"
    task["updatedAt"] = now_iso()
    write_db(db)
    return redirect(url_for("tasks_page"))


@app.post("/tasks/<task_id>/delete")
@login_required
def delete_task(task_id: str):
    db = read_db()
    before = len(db["tasks"])
    db["tasks"] = [t for t in db["tasks"] if not (t.get("id") == task_id and t.get("ownerId") == g.user["id"])]
    if len(db["tasks"]) == before:
        abort(404)
    write_db(db)
    flash("Tarea eliminada.", "success")
    return redirect(url_for("tasks_page"))


@app.route("/actividades")
@login_required
def activities_page():
    db = read_db()
    items = sorted([e for e in db["events"] if e.get("type") == "official"], key=lambda e: (e.get("date", ""), e.get("startTime", "")))
    return render_template("activities.html", items=items)


@app.route("/material")
@login_required
def material_page():
    db = read_db()
    uid = g.user["id"]
    materials = sorted(db["materials"], key=lambda m: m.get("createdAt", ""), reverse=True)
    comments = [
        {**c, "authorName": author_name(db, c.get("authorId", ""))}
        for c in db["materialComments"]
        if c.get("visibility") == "public" or c.get("authorId") == uid
    ]
    grouped_comments: dict[str, list[dict[str, Any]]] = {}
    for c in comments:
        grouped_comments.setdefault(c.get("materialId", ""), []).append(c)
    for values in grouped_comments.values():
        values.sort(key=lambda c: c.get("createdAt", ""), reverse=True)
    return render_template("material.html", materials=materials, grouped_comments=grouped_comments)


@app.post("/materials")
@roles_required("admin", "coordinator")
def create_material():
    try:
        file_name, original_name, mime = save_uploaded_file(request.files.get("file"))
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("material_page"))
    db = read_db()
    name = request.form.get("name", "").strip() or original_name or "Material"
    item = {
        "id": new_id(),
        "name": name[:180],
        "description": request.form.get("description", "").strip()[:5000],
        "category": request.form.get("category", "Otros"),
        "authorId": g.user["id"],
        "fileName": file_name,
        "originalName": original_name,
        "mime": mime,
        "url": request.form.get("url") or None,
        "createdAt": now_iso(),
    }
    db["materials"].insert(0, item)
    write_db(db)
    flash("Material publicado.", "success")
    return redirect(url_for("material_page"))


@app.route("/uploads/<path:filename>")
@login_required
def uploaded_file(filename: str):
    return send_from_directory(UPLOAD_DIR, filename, as_attachment=False)


@app.post("/materials/<material_id>/comments")
@login_required
def add_material_comment(material_id: str):
    db = read_db()
    if not any(m.get("id") == material_id for m in db["materials"]):
        abort(404)
    text = request.form.get("text", "").strip()
    if not text:
        flash("Escribe un comentario.", "error")
        return redirect(url_for("material_page"))
    visibility = "personal" if request.form.get("visibility") == "personal" else "public"
    db["materialComments"].insert(
        0,
        {
            "id": new_id(),
            "materialId": material_id,
            "authorId": g.user["id"],
            "text": text[:3000],
            "visibility": visibility,
            "createdAt": now_iso(),
            "updatedAt": now_iso(),
        },
    )
    write_db(db)
    flash("Comentario publicado." if visibility == "public" else "Comentario personal guardado.", "success")
    return redirect(url_for("material_page") + f"#material-{material_id}")


@app.post("/material-comments/<comment_id>/delete")
@login_required
def delete_material_comment(comment_id: str):
    db = read_db()
    comment = next((c for c in db["materialComments"] if c.get("id") == comment_id), None)
    if not comment:
        abort(404)
    allowed = comment.get("authorId") == g.user["id"] or (comment.get("visibility") == "public" and g.user.get("role") == "admin")
    if not allowed:
        abort(403)
    db["materialComments"] = [c for c in db["materialComments"] if c.get("id") != comment_id]
    write_db(db)
    flash("Comentario eliminado.", "success")
    return redirect(url_for("material_page") + f"#material-{comment.get('materialId')}")


@app.route("/mi-espacio")
@login_required
def space_page():
    db = read_db()
    uid = g.user["id"]
    today = date.today().isoformat()
    upcoming = sorted(
        [e for e in db["events"] if (e.get("type") == "official" or e.get("ownerId") == uid) and e.get("date", "") >= today],
        key=lambda e: (e.get("date", ""), e.get("startTime", "")),
    )[:5]
    notes = sorted([n for n in db["notes"] if n.get("ownerId") == uid], key=lambda n: n.get("createdAt", ""), reverse=True)
    return render_template("space.html", upcoming=upcoming, notes=notes)


@app.post("/notes")
@login_required
def create_note():
    text = request.form.get("text", "").strip()
    if text:
        db = read_db()
        db["notes"].insert(0, {"id": new_id(), "ownerId": g.user["id"], "text": text[:4000], "createdAt": now_iso(), "updatedAt": now_iso()})
        write_db(db)
        flash("Nota guardada.", "success")
    return redirect(url_for("space_page"))


@app.post("/notes/<note_id>/delete")
@login_required
def delete_note(note_id: str):
    db = read_db()
    db["notes"] = [n for n in db["notes"] if not (n.get("id") == note_id and n.get("ownerId") == g.user["id"])]
    write_db(db)
    return redirect(url_for("space_page"))


def attendance_payload(db: dict[str, Any]):
    students = [u for u in db["users"] if u.get("role") == "participant" and u.get("status") == "active"]
    summary = []
    for u in students:
        recs = [r for r in db["attendanceRecords"] if r.get("userId") == u.get("id")]
        present = sum(1 for r in recs if r.get("status") == "present")
        absent = sum(1 for r in recs if r.get("status") == "absent")
        late = sum(1 for r in recs if r.get("status") == "late")
        excused = sum(1 for r in recs if r.get("status") == "excused")
        counted = present + absent + late
        rate = round(((present + late) / counted) * 100) if counted else 100
        summary.append({**safe_user(u), "userId": u["id"], "present": present, "absent": absent, "late": late, "excused": excused, "total": len(recs), "rate": rate})
    sessions = []
    for s in db["attendanceSessions"]:
        event = next((e for e in db["events"] if e.get("id") == s.get("eventId")), None)
        sessions.append({**s, "eventTitle": event.get("title") if event else None, "recordsCount": sum(1 for r in db["attendanceRecords"] if r.get("sessionId") == s.get("id"))})
    sessions.sort(key=lambda s: (s.get("date", ""), s.get("createdAt", "")), reverse=True)
    return students, summary, sessions


@app.route("/asistencia")
@roles_required("admin", "coordinator")
def attendance_page():
    db = read_db()
    students, summary, sessions = attendance_payload(db)
    selected_id = request.args.get("session")
    selected = next((s for s in sessions if s.get("id") == selected_id), None)
    if selected is None and sessions:
        selected = sessions[0]
    record_map: dict[str, dict[str, Any]] = {}
    if selected:
        for r in db["attendanceRecords"]:
            if r.get("sessionId") == selected.get("id"):
                record_map[r.get("userId")] = r
        for student in students:
            record_map.setdefault(student["id"], {"status": "present", "note": ""})
    official_events = [e for e in db["events"] if e.get("type") == "official"]
    return render_template("attendance.html", sessions=sessions, summary=summary, students=students, selected=selected, record_map=record_map, official_events=official_events, today=date.today().isoformat())


@app.post("/attendance/sessions")
@roles_required("admin", "coordinator")
def create_attendance_session():
    title = request.form.get("title", "").strip()
    session_date = request.form.get("date", "").strip()
    event_id = request.form.get("eventId") or None
    db = read_db()
    if not title or not session_date:
        flash("Nombre y fecha son obligatorios.", "error")
        return redirect(url_for("attendance_page"))
    if event_id and not any(e.get("id") == event_id and e.get("type") == "official" for e in db["events"]):
        flash("Actividad relacionada inválida.", "error")
        return redirect(url_for("attendance_page"))
    item = {"id": new_id(), "title": title[:160], "date": session_date, "eventId": event_id, "createdBy": g.user["id"], "createdAt": now_iso(), "updatedAt": now_iso()}
    db["attendanceSessions"].append(item)
    write_db(db)
    flash("Lista creada. Ya puedes pasar asistencia.", "success")
    return redirect(url_for("attendance_page", session=item["id"]))


@app.post("/attendance/sessions/<session_id>/records")
@roles_required("admin", "coordinator")
def save_attendance_records(session_id: str):
    db = read_db()
    attendance_session = next((s for s in db["attendanceSessions"] if s.get("id") == session_id), None)
    if not attendance_session:
        abort(404)
    allowed_ids = {u["id"] for u in db["users"] if u.get("role") == "participant" and u.get("status") == "active"}
    for user_id in allowed_ids:
        status = request.form.get(f"status_{user_id}", "present")
        note = request.form.get(f"note_{user_id}", "").strip()[:500]
        if status not in ATTENDANCE_STATUSES:
            status = "present"
        index = next((i for i, r in enumerate(db["attendanceRecords"]) if r.get("sessionId") == session_id and r.get("userId") == user_id), -1)
        old = db["attendanceRecords"][index] if index >= 0 else None
        record = {
            "id": old.get("id") if old else new_id(),
            "sessionId": session_id,
            "userId": user_id,
            "status": status,
            "note": note,
            "takenBy": g.user["id"],
            "createdAt": old.get("createdAt") if old else now_iso(),
            "updatedAt": now_iso(),
        }
        if index >= 0:
            db["attendanceRecords"][index] = record
        else:
            db["attendanceRecords"].append(record)
    attendance_session["updatedAt"] = now_iso()
    write_db(db)
    flash("Lista de asistencia guardada.", "success")
    return redirect(url_for("attendance_page", session=session_id))


@app.route("/admin")
@roles_required("admin")
def admin_page():
    db = read_db()
    users = sorted([safe_user(u) for u in db["users"]], key=lambda u: (u.get("status") != "active", u.get("name", "").lower()))
    stats = {
        "active_users": sum(1 for u in db["users"] if u.get("status") == "active"),
        "activities": sum(1 for e in db["events"] if e.get("type") == "official"),
        "materials": len(db["materials"]),
        "attendance_sessions": len(db["attendanceSessions"]),
    }
    return render_template("admin.html", users=users, stats=stats)


@app.post("/users")
@roles_required("admin")
def create_user():
    db = read_db()
    email = request.form.get("email", "").strip().lower()
    name = request.form.get("name", "").strip()
    role = request.form.get("role", "participant")
    if role not in ROLES:
        role = "participant"
    if not email or not name:
        flash("Nombre y correo son obligatorios.", "error")
        return redirect(url_for("admin_page"))
    if any(u.get("email", "").lower() == email for u in db["users"]):
        flash("Ese correo ya está registrado.", "error")
        return redirect(url_for("admin_page"))
    user = {
        "id": new_id(),
        "name": name[:100],
        "lastName": request.form.get("lastName", "").strip()[:120],
        "email": email,
        "passwordHash": hash_password(request.form.get("password") or "Temporal2026!"),
        "role": role,
        "status": "active",
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
    }
    db["users"].append(user)
    write_db(db)
    flash("Usuario creado correctamente.", "success")
    return redirect(url_for("admin_page"))


@app.post("/users/<user_id>/update")
@roles_required("admin")
def update_user(user_id: str):
    db = read_db()
    user = next((u for u in db["users"] if u.get("id") == user_id), None)
    if not user:
        abort(404)
    role = request.form.get("role", user.get("role", "participant"))
    status = request.form.get("status", user.get("status", "active"))
    if role in ROLES:
        user["role"] = role
    if status in {"active", "inactive"}:
        user["status"] = status
    for key in ["name", "lastName", "email"]:
        if request.form.get(key) is not None:
            user[key] = request.form.get(key).strip()
    password = request.form.get("password", "").strip()
    if password:
        user["passwordHash"] = hash_password(password)
    user["updatedAt"] = now_iso()
    write_db(db)
    if user_id == g.user["id"] and status == "inactive":
        session.clear()
        return redirect(url_for("login"))
    flash("Usuario actualizado.", "success")
    return redirect(url_for("admin_page"))


@app.route("/notificaciones")
@login_required
def notifications_page():
    db = read_db()
    notifications = sorted([n for n in db["notifications"] if n.get("userId") == g.user["id"]], key=lambda n: n.get("createdAt", ""), reverse=True)
    return render_template("notifications.html", notifications=notifications)


@app.post("/notifications/<notification_id>/toggle")
@login_required
def toggle_notification(notification_id: str):
    db = read_db()
    n = next((n for n in db["notifications"] if n.get("id") == notification_id and n.get("userId") == g.user["id"]), None)
    if not n:
        abort(404)
    n["read"] = not n.get("read", False)
    write_db(db)
    return redirect(url_for("notifications_page"))


@app.post("/notifications/<notification_id>/delete")
@login_required
def delete_notification(notification_id: str):
    db = read_db()
    db["notifications"] = [n for n in db["notifications"] if not (n.get("id") == notification_id and n.get("userId") == g.user["id"])]
    write_db(db)
    return redirect(url_for("notifications_page"))


@app.route("/buscar")
@login_required
def search_page():
    q = request.args.get("q", "").strip().lower()
    db = read_db()
    uid = g.user["id"]
    results = {"events": [], "tasks": [], "materials": []}
    if q:
        results["events"] = [e for e in db["events"] if (e.get("type") == "official" or e.get("ownerId") == uid) and q in f"{e.get('title','')} {e.get('description','')}".lower()][:12]
        results["tasks"] = [t for t in db["tasks"] if (t.get("ownerId") == uid or t.get("assignedTo") == uid) and q in f"{t.get('title','')} {t.get('description','')}".lower()][:12]
        results["materials"] = [m for m in db["materials"] if q in f"{m.get('name','')} {m.get('description','')}".lower()][:12]
    return render_template("search.html", q=q, results=results)


if __name__ == "__main__":
    ensure_seed()
    print("+Q1LÍDER Flask listo en http://localhost:5000")
    print("Demo: admin@q1lider.local / Q1Lider2026!")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
else:
    ensure_seed()
