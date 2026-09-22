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
    jsonify,
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
    canonical_role,
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
    MAX_CONTENT_LENGTH=50 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

ALLOWED_EXTENSIONS = {
    "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "png", "jpg", "jpeg", "gif", "webp",
    "mp4", "webm", "mov", "mp3", "wav", "m4a", "txt", "csv", "zip"
}
IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
ROLES = {"admin", "teacher", "participant"}
STAFF_ROLES = {"admin", "teacher"}
ATTENDANCE_STATUSES = {"present", "absent", "late", "excused"}
MATERIAL_TYPES = {
    "module_plan": "Plan del módulo",
    "study_guide": "Guía de estudio complementaria",
    "case_statement": "Enunciado de caso práctico",
    "project_practical": "Enunciado práctico para proyecto",
    "master_class": "Master class / clase grabada",
    "resource": "Recurso complementario",
}
ASSESSMENT_TYPES = {"self_assessment": "Autoevaluación", "final_exam": "Examen final"}
BLOCK_AFTER_ABSENCES = 3
PROGRAM_WEEKS = 12


def role_of(user: dict[str, Any] | None) -> str:
    return canonical_role((user or {}).get("role"))


def is_staff(user: dict[str, Any] | None) -> bool:
    return role_of(user) in STAFF_ROLES


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


def absence_count(db: dict[str, Any], user_id: str) -> int:
    valid_session_ids = {
        s.get("id") for s in db["attendanceSessions"]
        if 1 <= int(s.get("weekNumber") or 0) <= PROGRAM_WEEKS
    }
    # Old attendance sessions without a week still count so existing data is not lost.
    old_session_ids = {s.get("id") for s in db["attendanceSessions"] if not s.get("weekNumber")}
    valid_session_ids |= old_session_ids
    return sum(
        1 for r in db["attendanceRecords"]
        if r.get("userId") == user_id and r.get("status") == "absent" and r.get("sessionId") in valid_session_ids
    )


def user_is_attendance_blocked(db: dict[str, Any], user: dict[str, Any] | None) -> bool:
    return bool(user and role_of(user) == "participant" and absence_count(db, user.get("id", "")) >= BLOCK_AFTER_ABSENCES)


@app.before_request
def load_user_and_enforce_attendance() -> None:
    g.user = current_user()
    g.attendance_blocked = False
    g.absence_count = 0
    if not g.user:
        return
    if role_of(g.user) == "participant":
        db = read_db()
        g.absence_count = absence_count(db, g.user["id"])
        g.attendance_blocked = g.absence_count >= BLOCK_AFTER_ABSENCES
        allowed = {"blocked_page", "logout", "static", "set_theme_preference"}
        if g.attendance_blocked and request.endpoint not in allowed:
            return redirect(url_for("blocked_page"))


@app.context_processor
def inject_globals() -> dict[str, Any]:
    unread = 0
    if g.get("user"):
        db = read_db()
        unread = sum(1 for n in db["notifications"] if n.get("userId") == g.user["id"] and not n.get("read"))
    return {
        "current_user": safe_user(g.user) if g.get("user") else None,
        "unread_notifications": unread,
        "attendance_blocked": bool(g.get("attendance_blocked")),
        "absence_count": int(g.get("absence_count") or 0),
        "material_type_labels": MATERIAL_TYPES,
        "assessment_type_labels": ASSESSMENT_TYPES,
    }


def login_required(view: Callable) -> Callable:
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not g.get("user"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def roles_required(*roles: str) -> Callable:
    accepted = {canonical_role(r) for r in roles}
    def decorator(view: Callable) -> Callable:
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if role_of(g.user) not in accepted:
                flash("No tienes permisos para realizar esa acción.", "error")
                return redirect(url_for("calendar_page"))
            return view(*args, **kwargs)
        return wrapped
    return decorator


def author_name(db: dict[str, Any], user_id: str) -> str:
    user = next((u for u in db["users"] if u.get("id") == user_id), None)
    return f"{user.get('name', '')} {user.get('lastName', '')}".strip() if user else "Usuario"


def can_manage_event(event: dict[str, Any], user: dict[str, Any]) -> bool:
    if event.get("type") == "personal":
        return event.get("ownerId") == user.get("id")
    return is_staff(user)


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


def save_event_image(file_storage) -> tuple[str | None, str | None, str | None]:
    if not file_storage or not file_storage.filename:
        return None, None, None
    original = secure_filename(file_storage.filename)
    extension = original.rsplit(".", 1)[-1].lower() if "." in original else ""
    if not original or extension not in IMAGE_EXTENSIONS:
        raise ValueError("La imagen debe ser PNG, JPG, JPEG, GIF o WEBP.")
    stamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    filename = f"event-{stamp}-{original}"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    file_storage.save(UPLOAD_DIR / filename)
    return filename, original, file_storage.mimetype


def get_module(db: dict[str, Any], module_id: str | None) -> dict[str, Any] | None:
    return next((m for m in db["modules"] if m.get("id") == module_id), None)


def survey_completed(db: dict[str, Any], module_id: str, user_id: str) -> bool:
    return any(r.get("moduleId") == module_id and r.get("userId") == user_id for r in db["surveyResponses"])


def grade_for_item(db: dict[str, Any], grade_item_id: str, user_id: str) -> float | None:
    row = next((g for g in db["grades"] if g.get("gradeItemId") == grade_item_id and g.get("userId") == user_id), None)
    if not row:
        return None
    try:
        return float(row.get("score", 0))
    except (TypeError, ValueError):
        return None


def module_grade(db: dict[str, Any], module_id: str, user_id: str) -> dict[str, Any]:
    items = [i for i in db["gradeItems"] if i.get("moduleId") == module_id]
    total_weight = sum(float(i.get("weight") or 0) for i in items)
    earned = 0.0
    graded_weight = 0.0
    details = []
    for item in items:
        weight = float(item.get("weight") or 0)
        score = grade_for_item(db, item["id"], user_id)
        if score is not None:
            earned += score * weight / 100.0
            graded_weight += weight
        details.append({**item, "score": score})
    # Grade is computed over configured weight, which reflects activity values.
    value = round((earned / total_weight) * 100, 1) if total_weight > 0 else None
    return {
        "grade": value,
        "totalWeight": round(total_weight, 2),
        "gradedWeight": round(graded_weight, 2),
        "details": details,
    }


def module_absences(db: dict[str, Any], module_id: str, user_id: str) -> int:
    session_ids = {s.get("id") for s in db["attendanceSessions"] if s.get("moduleId") == module_id}
    return sum(1 for r in db["attendanceRecords"] if r.get("sessionId") in session_ids and r.get("userId") == user_id and r.get("status") == "absent")


def upsert_grade(db: dict[str, Any], grade_item_id: str, user_id: str, score: float, graded_by: str) -> None:
    score = max(0.0, min(100.0, float(score)))
    existing = next((g for g in db["grades"] if g.get("gradeItemId") == grade_item_id and g.get("userId") == user_id), None)
    if existing:
        existing.update({"score": score, "gradedBy": graded_by, "updatedAt": now_iso()})
    else:
        db["grades"].append({
            "id": new_id(), "gradeItemId": grade_item_id, "userId": user_id, "score": score,
            "gradedBy": graded_by, "createdAt": now_iso(), "updatedAt": now_iso(),
        })


@app.errorhandler(413)
def file_too_large(_):
    flash("El archivo supera el límite de 50 MB.", "error")
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
            if user_is_attendance_blocked(db, user):
                return redirect(url_for("blocked_page"))
            return redirect(request.args.get("next") or url_for("calendar_page"))
    return render_template("login.html")


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.post("/preferencias/tema")
@login_required
def set_theme_preference():
    payload = request.get_json(silent=True) or request.form
    theme = str(payload.get("theme", "")).strip().lower()
    if theme not in {"light", "dark"}:
        return jsonify({"ok": False, "error": "Tema no válido"}), 400

    db = read_db()
    user = next((u for u in db["users"] if u.get("id") == g.user.get("id")), None)
    if not user:
        return jsonify({"ok": False, "error": "Usuario no encontrado"}), 404

    user["theme"] = theme
    user["updatedAt"] = now_iso()
    write_db(db)
    # Keep the current request context in sync so any subsequent rendering uses the same preference.
    g.user["theme"] = theme
    return jsonify({"ok": True, "theme": theme})


@app.route("/bloqueado")
@login_required
def blocked_page():
    db = read_db()
    count = absence_count(db, g.user["id"])
    if role_of(g.user) != "participant" or count < BLOCK_AFTER_ABSENCES:
        return redirect(url_for("calendar_page"))
    return render_template("blocked.html", count=count, limit=BLOCK_AFTER_ABSENCES)


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

    start = first - timedelta(days=(first.weekday() + 1) % 7)
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
        "calendar.html", days=days, year=year, month=month,
        month_name=["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"][month],
        prev=prev, next_month=next_month, filter_name=filter_name, announcements=announcements,
        mobile_agenda=mobile_agenda, today=today,
    )


@app.post("/events")
@login_required
def create_event():
    event_type = "official" if request.form.get("type") == "official" else "personal"
    if event_type == "official" and not is_staff(g.user):
        abort(403)
    title = request.form.get("title", "").strip()
    event_date = request.form.get("date", "").strip()
    if not title or not event_date:
        flash("Título y fecha son obligatorios.", "error")
        return redirect(request.referrer or url_for("calendar_page"))
    db = read_db()
    try:
        image_name, image_original, image_mime = save_event_image(request.files.get("image"))
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(request.referrer or url_for("calendar_page"))
    item = {
        "id": new_id(), "title": title[:180], "description": request.form.get("description", "").strip()[:5000],
        "date": event_date, "startTime": request.form.get("startTime", "09:00"), "endTime": request.form.get("endTime", "10:00"),
        "place": request.form.get("place", "").strip()[:250], "type": event_type,
        "status": request.form.get("status", "pending"), "priority": request.form.get("priority", "medium"),
        "category": request.form.get("category", ""), "ownerId": g.user["id"], "responsibleId": g.user["id"],
        "imageName": image_name, "imageOriginal": image_original, "imageMime": image_mime,
        "participants": [], "checklist": [], "createdAt": now_iso(), "updatedAt": now_iso(),
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
    if request.form.get("removeImage") == "1":
        event["imageName"] = None
        event["imageOriginal"] = None
        event["imageMime"] = None
    try:
        image_name, image_original, image_mime = save_event_image(request.files.get("image"))
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(request.referrer or url_for("activities_page"))
    if image_name:
        event["imageName"] = image_name
        event["imageOriginal"] = image_original
        event["imageMime"] = image_mime
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
    return redirect(request.referrer or url_for("activities_page"))


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
    db["tasks"].append({
        "id": new_id(), "title": title[:180], "description": request.form.get("description", "").strip()[:5000],
        "dueDate": request.form.get("dueDate") or None, "priority": request.form.get("priority", "medium"),
        "status": request.form.get("status", "pending"), "ownerId": g.user["id"], "personal": True,
        "checklist": [], "createdAt": now_iso(), "updatedAt": now_iso(),
    })
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


# --------------------------- ACADEMIC MODULES ---------------------------
@app.route("/modulos")
@login_required
def modules_page():
    db = read_db()
    uid = g.user["id"]
    cards = []
    for module in sorted(db["modules"], key=lambda m: int(m.get("number") or 0)):
        materials_count = sum(1 for m in db["materials"] if m.get("moduleId") == module["id"])
        assessments = [a for a in db["assessments"] if a.get("moduleId") == module["id"]]
        attempts = [a for a in db["assessmentAttempts"] if a.get("userId") == uid and any(x.get("id") == a.get("assessmentId") for x in assessments)]
        survey_done = survey_completed(db, module["id"], uid) if role_of(g.user) == "participant" else False
        mg = module_grade(db, module["id"], uid) if role_of(g.user) == "participant" else {"grade": None}
        cards.append({**module, "materialsCount": materials_count, "assessmentCount": len(assessments), "attemptCount": len(attempts), "surveyDone": survey_done, "grade": mg.get("grade")})
    return render_template("modules.html", modules=cards)


@app.route("/modulos/<module_id>")
@login_required
def module_detail(module_id: str):
    db = read_db()
    module = get_module(db, module_id)
    if not module:
        abort(404)
    uid = g.user["id"]
    materials = [m for m in db["materials"] if m.get("moduleId") == module_id]
    grouped: dict[str, list[dict[str, Any]]] = {k: [] for k in MATERIAL_TYPES}
    for item in materials:
        grouped.setdefault(item.get("contentType") or "resource", []).append(item)
    comments = [
        {**c, "authorName": author_name(db, c.get("authorId", ""))}
        for c in db["materialComments"]
        if c.get("materialId") in {m.get("id") for m in materials}
        and (c.get("visibility") == "public" or c.get("authorId") == uid)
    ]
    grouped_comments: dict[str, list[dict[str, Any]]] = {}
    for c in comments:
        grouped_comments.setdefault(c.get("materialId", ""), []).append(c)
    posts = sorted([
        {**p, "authorName": author_name(db, p.get("authorId", ""))}
        for p in db["forumPosts"] if p.get("moduleId") == module_id
    ], key=lambda p: p.get("createdAt", ""))
    assessments = sorted([a for a in db["assessments"] if a.get("moduleId") == module_id], key=lambda a: a.get("createdAt", ""))
    attempts_by_exam = {}
    for attempt in db["assessmentAttempts"]:
        if attempt.get("userId") == uid:
            attempts_by_exam.setdefault(attempt.get("assessmentId"), []).append(attempt)
    survey = next((s for s in db["surveys"] if s.get("moduleId") == module_id), None)
    survey_done = survey_completed(db, module_id, uid)
    submission = next((s for s in db["submissions"] if s.get("moduleId") == module_id and s.get("userId") == uid), None)
    grade_data = module_grade(db, module_id, uid) if role_of(g.user) == "participant" else None
    return render_template(
        "module_detail.html", module=module, grouped=grouped, posts=posts, assessments=assessments,
        attempts_by_exam=attempts_by_exam, survey=survey, survey_done=survey_done, submission=submission,
        grouped_comments=grouped_comments, grade_data=grade_data,
    )


@app.post("/modulos/<module_id>/update")
@roles_required("admin", "teacher")
def update_module(module_id: str):
    db = read_db()
    module = get_module(db, module_id)
    if not module:
        abort(404)
    module["title"] = request.form.get("title", module.get("title", "")).strip()[:160]
    module["subtitle"] = request.form.get("subtitle", module.get("subtitle", "")).strip()[:200]
    module["description"] = request.form.get("description", module.get("description", "")).strip()[:5000]
    module["updatedAt"] = now_iso()
    write_db(db)
    flash("Módulo actualizado.", "success")
    return redirect(url_for("module_detail", module_id=module_id))


@app.post("/modulos/<module_id>/foro")
@login_required
def create_forum_post(module_id: str):
    db = read_db()
    if not get_module(db, module_id):
        abort(404)
    text = request.form.get("text", "").strip()
    if not text:
        flash("Escribe tu duda o comentario.", "error")
        return redirect(url_for("module_detail", module_id=module_id) + "#foro")
    db["forumPosts"].append({
        "id": new_id(), "moduleId": module_id, "authorId": g.user["id"], "text": text[:5000],
        "createdAt": now_iso(), "updatedAt": now_iso(),
    })
    write_db(db)
    flash("Tu mensaje se publicó en el foro.", "success")
    return redirect(url_for("module_detail", module_id=module_id) + "#foro")


@app.post("/foro/<post_id>/delete")
@login_required
def delete_forum_post(post_id: str):
    db = read_db()
    post = next((p for p in db["forumPosts"] if p.get("id") == post_id), None)
    if not post:
        abort(404)
    if post.get("authorId") != g.user["id"] and not is_staff(g.user):
        abort(403)
    db["forumPosts"] = [p for p in db["forumPosts"] if p.get("id") != post_id]
    write_db(db)
    flash("Mensaje eliminado.", "success")
    return redirect(url_for("module_detail", module_id=post.get("moduleId")) + "#foro")


@app.post("/modulos/<module_id>/entrega-caso")
@roles_required("participant")
def submit_case(module_id: str):
    db = read_db()
    if not get_module(db, module_id):
        abort(404)
    try:
        file_name, original_name, mime = save_uploaded_file(request.files.get("file"))
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("module_detail", module_id=module_id))
    if not file_name:
        flash("Selecciona un archivo para entregar.", "error")
        return redirect(url_for("module_detail", module_id=module_id))
    existing = next((s for s in db["submissions"] if s.get("moduleId") == module_id and s.get("userId") == g.user["id"]), None)
    payload = {
        "moduleId": module_id, "userId": g.user["id"], "fileName": file_name, "originalName": original_name,
        "mime": mime, "note": request.form.get("note", "").strip()[:2000], "updatedAt": now_iso(),
    }
    if existing:
        existing.update(payload)
    else:
        db["submissions"].append({"id": new_id(), **payload, "createdAt": now_iso()})
    write_db(db)
    flash("Caso práctico entregado correctamente.", "success")
    return redirect(url_for("module_detail", module_id=module_id))


@app.post("/modulos/<module_id>/encuesta")
@roles_required("participant")
def submit_survey(module_id: str):
    db = read_db()
    survey = next((s for s in db["surveys"] if s.get("moduleId") == module_id), None)
    if not survey:
        abort(404)
    if survey_completed(db, module_id, g.user["id"]):
        flash("Ya completaste la encuesta de este módulo.", "success")
        return redirect(url_for("module_detail", module_id=module_id) + "#evaluaciones")
    answers = {}
    for q in survey.get("questions", []):
        value = request.form.get(f"q_{q['id']}", "").strip()
        if not value:
            flash("Responde todas las preguntas de la encuesta.", "error")
            return redirect(url_for("module_detail", module_id=module_id) + "#encuesta")
        answers[q["id"]] = value[:3000]
    db["surveyResponses"].append({
        "id": new_id(), "surveyId": survey["id"], "moduleId": module_id, "userId": g.user["id"],
        "answers": answers, "createdAt": now_iso(),
    })
    write_db(db)
    flash("Encuesta completada. El examen final ya está desbloqueado.", "success")
    return redirect(url_for("module_detail", module_id=module_id) + "#evaluaciones")


# --------------------------- MATERIALS ---------------------------
@app.route("/material")
@login_required
def material_page():
    db = read_db()
    uid = g.user["id"]
    module_filter = request.args.get("module") or ""
    materials = sorted(db["materials"], key=lambda m: m.get("createdAt", ""), reverse=True)
    if module_filter:
        materials = [m for m in materials if m.get("moduleId") == module_filter]
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
    module_map = {m["id"]: m for m in db["modules"]}
    return render_template("material.html", materials=materials, grouped_comments=grouped_comments, modules=db["modules"], module_map=module_map, module_filter=module_filter)


@app.post("/materials")
@roles_required("admin", "teacher")
def create_material():
    try:
        file_name, original_name, mime = save_uploaded_file(request.files.get("file"))
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(request.referrer or url_for("material_page"))
    db = read_db()
    name = request.form.get("name", "").strip() or original_name or "Material"
    module_id = request.form.get("moduleId") or None
    if module_id and not get_module(db, module_id):
        module_id = None
    content_type = request.form.get("contentType", "resource")
    if content_type not in MATERIAL_TYPES:
        content_type = "resource"
    item = {
        "id": new_id(), "name": name[:180], "description": request.form.get("description", "").strip()[:5000],
        "category": request.form.get("category", "Otros"), "contentType": content_type, "moduleId": module_id,
        "authorId": g.user["id"], "fileName": file_name, "originalName": original_name, "mime": mime,
        "url": request.form.get("url") or None, "createdAt": now_iso(), "updatedAt": now_iso(),
    }
    db["materials"].insert(0, item)
    write_db(db)
    flash("Material publicado.", "success")
    return redirect(request.referrer or url_for("material_page"))


@app.post("/materials/<material_id>/update")
@roles_required("admin", "teacher")
def update_material(material_id: str):
    db = read_db()
    material = next((m for m in db["materials"] if m.get("id") == material_id), None)
    if not material:
        abort(404)
    content_type = request.form.get("contentType", material.get("contentType", "resource"))
    if content_type not in MATERIAL_TYPES:
        content_type = "resource"
    material["name"] = request.form.get("name", material.get("name", "Material")).strip()[:180]
    material["description"] = request.form.get("description", material.get("description", "")).strip()[:5000]
    material["contentType"] = content_type
    material["url"] = request.form.get("url", "").strip() or None
    try:
        file_name, original_name, mime = save_uploaded_file(request.files.get("file"))
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(request.referrer or url_for("material_page"))
    if file_name:
        material["fileName"] = file_name
        material["originalName"] = original_name
        material["mime"] = mime
    material["updatedAt"] = now_iso()
    write_db(db)
    flash("Contenido del módulo actualizado.", "success")
    return redirect(request.referrer or url_for("material_page"))


@app.post("/materials/<material_id>/delete")
@roles_required("admin", "teacher")
def delete_material(material_id: str):
    db = read_db()
    material = next((m for m in db["materials"] if m.get("id") == material_id), None)
    if not material:
        abort(404)
    db["materials"] = [m for m in db["materials"] if m.get("id") != material_id]
    db["materialComments"] = [c for c in db["materialComments"] if c.get("materialId") != material_id]
    write_db(db)
    flash("Contenido eliminado.", "success")
    module_id = material.get("moduleId")
    return redirect(url_for("module_detail", module_id=module_id) if module_id else url_for("material_page"))


@app.route("/uploads/<path:filename>")
@login_required
def uploaded_file(filename: str):
    return send_from_directory(UPLOAD_DIR, filename, as_attachment=False)


@app.post("/materials/<material_id>/comments")
@login_required
def add_material_comment(material_id: str):
    db = read_db()
    material = next((m for m in db["materials"] if m.get("id") == material_id), None)
    if not material:
        abort(404)
    text = request.form.get("text", "").strip()
    if not text:
        flash("Escribe un comentario.", "error")
        return redirect(request.referrer or url_for("material_page"))
    visibility = "personal" if request.form.get("visibility") == "personal" else "public"
    db["materialComments"].insert(0, {
        "id": new_id(), "materialId": material_id, "authorId": g.user["id"], "text": text[:3000],
        "visibility": visibility, "createdAt": now_iso(), "updatedAt": now_iso(),
    })
    write_db(db)
    flash("Comentario publicado." if visibility == "public" else "Comentario personal guardado.", "success")
    return redirect(request.referrer or url_for("material_page") + f"#material-{material_id}")


@app.post("/material-comments/<comment_id>/delete")
@login_required
def delete_material_comment(comment_id: str):
    db = read_db()
    comment = next((c for c in db["materialComments"] if c.get("id") == comment_id), None)
    if not comment:
        abort(404)
    allowed = comment.get("authorId") == g.user["id"] or (comment.get("visibility") == "public" and is_staff(g.user))
    if not allowed:
        abort(403)
    db["materialComments"] = [c for c in db["materialComments"] if c.get("id") != comment_id]
    write_db(db)
    flash("Comentario eliminado.", "success")
    return redirect(request.referrer or url_for("material_page"))


# --------------------------- EXAMS / ASSESSMENTS ---------------------------
def parse_questions(raw: str) -> list[dict[str, Any]]:
    """Format: question|option A|option B|option C|correct option number (1-3)."""
    questions = []
    for line in raw.splitlines():
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 5 or not parts[0]:
            continue
        options = parts[1:-1]
        try:
            correct = int(parts[-1]) - 1
        except ValueError:
            continue
        if not options or correct < 0 or correct >= len(options):
            continue
        questions.append({"id": new_id(), "text": parts[0], "options": options, "correctIndex": correct})
    return questions


@app.route("/examenes")
@roles_required("admin", "teacher")
def exams_page():
    db = read_db()
    exams = []
    for exam in db["assessments"]:
        module = get_module(db, exam.get("moduleId"))
        attempts = [a for a in db["assessmentAttempts"] if a.get("assessmentId") == exam.get("id")]
        avg = round(sum(float(a.get("score") or 0) for a in attempts) / len(attempts), 1) if attempts else None
        exams.append({**exam, "moduleTitle": module.get("title") if module else "Sin módulo", "attemptCount": len(attempts), "average": avg})
    exams.sort(key=lambda x: x.get("createdAt", ""), reverse=True)
    return render_template("exams.html", exams=exams, modules=db["modules"])


@app.post("/examenes")
@roles_required("admin", "teacher")
def create_exam():
    db = read_db()
    module_id = request.form.get("moduleId") or ""
    if not get_module(db, module_id):
        flash("Selecciona un módulo válido.", "error")
        return redirect(url_for("exams_page"))
    exam_type = request.form.get("type", "self_assessment")
    if exam_type not in ASSESSMENT_TYPES:
        exam_type = "self_assessment"
    questions = parse_questions(request.form.get("questions", ""))
    if not questions:
        flash("Agrega al menos una pregunta con el formato indicado.", "error")
        return redirect(url_for("exams_page"))
    title = request.form.get("title", "").strip() or ASSESSMENT_TYPES[exam_type]
    assessment_id = new_id()
    grade_item_id = None
    try:
        weight = float(request.form.get("weight") or 0)
    except ValueError:
        weight = 0
    weight = max(0, min(100, weight))
    if weight > 0:
        grade_item_id = new_id()
        db["gradeItems"].append({
            "id": grade_item_id, "moduleId": module_id, "title": title, "type": exam_type,
            "weight": weight, "createdBy": g.user["id"], "createdAt": now_iso(), "updatedAt": now_iso(),
        })
    db["assessments"].append({
        "id": assessment_id, "moduleId": module_id, "title": title[:180], "description": request.form.get("description", "").strip()[:3000],
        "type": exam_type, "questions": questions, "gradeItemId": grade_item_id,
        "createdBy": g.user["id"], "createdAt": now_iso(), "updatedAt": now_iso(),
    })
    write_db(db)
    flash("Evaluación creada correctamente.", "success")
    return redirect(url_for("exams_page"))


@app.route("/examenes/<exam_id>/editar", methods=["GET", "POST"])
@roles_required("admin", "teacher")
def edit_exam(exam_id: str):
    db = read_db()
    exam = next((a for a in db["assessments"] if a.get("id") == exam_id), None)
    if not exam:
        abort(404)
    if request.method == "POST":
        module_id = request.form.get("moduleId") or exam.get("moduleId")
        if not get_module(db, module_id):
            flash("Selecciona un módulo válido.", "error")
            return redirect(url_for("edit_exam", exam_id=exam_id))
        exam_type = request.form.get("type", exam.get("type", "self_assessment"))
        if exam_type not in ASSESSMENT_TYPES:
            exam_type = "self_assessment"
        questions = parse_questions(request.form.get("questions", ""))
        if not questions:
            flash("Agrega al menos una pregunta válida.", "error")
            return redirect(url_for("edit_exam", exam_id=exam_id))
        title = request.form.get("title", "").strip() or ASSESSMENT_TYPES[exam_type]
        try:
            weight = max(0.0, min(100.0, float(request.form.get("weight") or 0)))
        except ValueError:
            weight = 0.0
        exam.update({
            "moduleId": module_id, "title": title[:180],
            "description": request.form.get("description", "").strip()[:3000],
            "type": exam_type, "questions": questions, "updatedAt": now_iso(),
        })
        grade_item = next((i for i in db["gradeItems"] if i.get("id") == exam.get("gradeItemId")), None)
        if weight > 0:
            if grade_item:
                grade_item.update({"moduleId": module_id, "title": title[:180], "type": exam_type, "weight": weight, "updatedAt": now_iso()})
            else:
                grade_item_id = new_id()
                db["gradeItems"].append({
                    "id": grade_item_id, "moduleId": module_id, "title": title[:180], "type": exam_type,
                    "weight": weight, "createdBy": g.user["id"], "createdAt": now_iso(), "updatedAt": now_iso(),
                })
                exam["gradeItemId"] = grade_item_id
        elif grade_item:
            db["gradeItems"] = [i for i in db["gradeItems"] if i.get("id") != grade_item.get("id")]
            db["grades"] = [gr for gr in db["grades"] if gr.get("gradeItemId") != grade_item.get("id")]
            exam["gradeItemId"] = None
        write_db(db)
        flash("Evaluación actualizada.", "success")
        return redirect(url_for("exams_page"))
    grade_item = next((i for i in db["gradeItems"] if i.get("id") == exam.get("gradeItemId")), None)
    question_lines = []
    for q in exam.get("questions", []):
        options = [str(o) for o in q.get("options", [])]
        correct_number = int(q.get("correctIndex", 0)) + 1
        question_lines.append("|".join([str(q.get("text", "")), *options, str(correct_number)]))
    return render_template(
        "edit_exam.html", exam=exam, modules=db["modules"], grade_item=grade_item,
        questions_text="\n".join(question_lines),
    )


@app.post("/examenes/<exam_id>/delete")
@roles_required("admin", "teacher")
def delete_exam(exam_id: str):
    db = read_db()
    exam = next((a for a in db["assessments"] if a.get("id") == exam_id), None)
    if not exam:
        abort(404)
    db["assessments"] = [a for a in db["assessments"] if a.get("id") != exam_id]
    db["assessmentAttempts"] = [a for a in db["assessmentAttempts"] if a.get("assessmentId") != exam_id]
    if exam.get("gradeItemId"):
        db["gradeItems"] = [i for i in db["gradeItems"] if i.get("id") != exam.get("gradeItemId")]
        db["grades"] = [g for g in db["grades"] if g.get("gradeItemId") != exam.get("gradeItemId")]
    write_db(db)
    flash("Evaluación eliminada.", "success")
    return redirect(url_for("exams_page"))


@app.route("/evaluacion/<exam_id>")
@roles_required("participant")
def take_exam(exam_id: str):
    db = read_db()
    exam = next((a for a in db["assessments"] if a.get("id") == exam_id), None)
    if not exam:
        abort(404)
    module = get_module(db, exam.get("moduleId"))
    if exam.get("type") == "final_exam" and not survey_completed(db, exam.get("moduleId"), g.user["id"]):
        flash("Completa primero la encuesta del módulo para desbloquear el examen final.", "error")
        return redirect(url_for("module_detail", module_id=exam.get("moduleId")) + "#encuesta")
    previous = next((a for a in db["assessmentAttempts"] if a.get("assessmentId") == exam_id and a.get("userId") == g.user["id"]), None)
    if previous:
        flash("Esta evaluación ya fue enviada y no puede volver a abrirse.", "error")
        return redirect(url_for("module_detail", module_id=exam.get("moduleId")) + "#evaluaciones")
    return render_template("take_exam.html", exam=exam, module=module, previous=None, locked_attempt=False)


@app.route("/evaluacion/<exam_id>/resultado")
@roles_required("participant")
def exam_result(exam_id: str):
    db = read_db()
    exam = next((a for a in db["assessments"] if a.get("id") == exam_id), None)
    if not exam:
        abort(404)
    attempt = next((a for a in db["assessmentAttempts"] if a.get("assessmentId") == exam_id and a.get("userId") == g.user["id"]), None)
    if not attempt:
        return redirect(url_for("take_exam", exam_id=exam_id))
    module = get_module(db, exam.get("moduleId"))
    return render_template("exam_result.html", exam=exam, attempt=attempt, module=module)


@app.post("/evaluacion/<exam_id>")
@roles_required("participant")
def submit_exam(exam_id: str):
    db = read_db()
    exam = next((a for a in db["assessments"] if a.get("id") == exam_id), None)
    if not exam:
        abort(404)
    if exam.get("type") == "final_exam" and not survey_completed(db, exam.get("moduleId"), g.user["id"]):
        abort(403)
    existing = next((a for a in db["assessmentAttempts"] if a.get("assessmentId") == exam_id and a.get("userId") == g.user["id"]), None)
    if existing:
        flash("Esta evaluación ya fue enviada y no puede volver a abrirse.", "error")
        return redirect(url_for("module_detail", module_id=exam.get("moduleId")) + "#evaluaciones")
    correct = 0
    answers = {}
    questions = exam.get("questions", [])
    for q in questions:
        raw = request.form.get(f"q_{q['id']}")
        try:
            answer = int(raw)
        except (TypeError, ValueError):
            answer = -1
        answers[q["id"]] = answer
        if answer == int(q.get("correctIndex", -2)):
            correct += 1
    score = round(correct * 100 / len(questions), 1) if questions else 0
    attempt = {
        "id": new_id(), "assessmentId": exam_id, "userId": g.user["id"], "answers": answers,
        "correct": correct, "total": len(questions), "score": score, "createdAt": now_iso(),
    }
    db["assessmentAttempts"].append(attempt)
    if exam.get("gradeItemId"):
        upsert_grade(db, exam["gradeItemId"], g.user["id"], score, g.user["id"])
    write_db(db)
    flash(f"Evaluación enviada. Calificación: {score}/100. Tu intento quedó cerrado definitivamente.", "success")
    return redirect(url_for("module_detail", module_id=exam.get("moduleId")) + "#evaluaciones")


# --------------------------- GRADES / KARDEX ---------------------------
@app.route("/calificaciones")
@roles_required("admin", "teacher")
def gradebook_page():
    db = read_db()
    module_id = request.args.get("module") or (db["modules"][0]["id"] if db["modules"] else "")
    module = get_module(db, module_id)
    students = [safe_user(u) for u in db["users"] if role_of(u) == "participant" and u.get("status") == "active"]
    items = [i for i in db["gradeItems"] if i.get("moduleId") == module_id]
    rows = []
    for student in students:
        grades = {item["id"]: grade_for_item(db, item["id"], student["id"]) for item in items}
        rows.append({"student": student, "grades": grades, "moduleGrade": module_grade(db, module_id, student["id"])["grade"]})
    total_weight = round(sum(float(i.get("weight") or 0) for i in items), 2)
    return render_template("gradebook.html", modules=db["modules"], module=module, items=items, rows=rows, total_weight=total_weight)


@app.post("/calificaciones/items")
@roles_required("admin", "teacher")
def create_grade_item():
    db = read_db()
    module_id = request.form.get("moduleId") or ""
    if not get_module(db, module_id):
        abort(400)
    title = request.form.get("title", "").strip()
    try:
        weight = float(request.form.get("weight") or 0)
    except ValueError:
        weight = 0
    if not title or weight <= 0 or weight > 100:
        flash("Indica un nombre y un valor entre 0 y 100%.", "error")
        return redirect(url_for("gradebook_page", module=module_id))
    db["gradeItems"].append({
        "id": new_id(), "moduleId": module_id, "title": title[:180], "type": request.form.get("type", "activity"),
        "weight": weight, "createdBy": g.user["id"], "createdAt": now_iso(), "updatedAt": now_iso(),
    })
    write_db(db)
    flash("Actividad calificable agregada.", "success")
    return redirect(url_for("gradebook_page", module=module_id))


@app.post("/calificaciones/<module_id>/guardar")
@roles_required("admin", "teacher")
def save_grades(module_id: str):
    db = read_db()
    if not get_module(db, module_id):
        abort(404)
    items = [i for i in db["gradeItems"] if i.get("moduleId") == module_id]
    students = [u for u in db["users"] if role_of(u) == "participant" and u.get("status") == "active"]
    for student in students:
        for item in items:
            raw = request.form.get(f"grade_{student['id']}_{item['id']}", "").strip()
            if raw == "":
                continue
            try:
                score = float(raw)
            except ValueError:
                continue
            upsert_grade(db, item["id"], student["id"], score, g.user["id"])
    write_db(db)
    flash("Calificaciones guardadas.", "success")
    return redirect(url_for("gradebook_page", module=module_id))


@app.route("/kardex")
@login_required
def kardex_page():
    db = read_db()
    requested = request.args.get("student")
    if is_staff(g.user) and requested:
        student = next((u for u in db["users"] if u.get("id") == requested and role_of(u) == "participant"), None)
    else:
        student = g.user if role_of(g.user) == "participant" else next((u for u in db["users"] if role_of(u) == "participant"), None)
    if not student:
        flash("No hay alumnos para mostrar en el Kárdex.", "error")
        return redirect(url_for("calendar_page"))
    rows = []
    grade_values = []
    for module in sorted(db["modules"], key=lambda m: int(m.get("number") or 0)):
        mg = module_grade(db, module["id"], student["id"])
        if mg["grade"] is not None:
            grade_values.append(mg["grade"])
        final_exam = next((a for a in db["assessments"] if a.get("moduleId") == module["id"] and a.get("type") == "final_exam"), None)
        final_attempt = None
        if final_exam:
            attempts = [a for a in db["assessmentAttempts"] if a.get("assessmentId") == final_exam["id"] and a.get("userId") == student["id"]]
            if attempts:
                final_attempt = sorted(attempts, key=lambda a: a.get("createdAt", ""), reverse=True)[0]
        rows.append({
            "module": module, "grade": mg["grade"], "weight": mg["totalWeight"], "absences": module_absences(db, module["id"], student["id"]),
            "surveyDone": survey_completed(db, module["id"], student["id"]), "finalScore": final_attempt.get("score") if final_attempt else None,
        })
    overall = round(sum(grade_values) / len(grade_values), 1) if grade_values else None
    students = [safe_user(u) for u in db["users"] if role_of(u) == "participant"] if is_staff(g.user) else []
    return render_template("kardex.html", student=safe_user(student), rows=rows, overall=overall, total_absences=absence_count(db, student["id"]), students=students)


# --------------------------- PERSONAL SPACE ---------------------------
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


@app.post("/notes/<note_id>/update")
@login_required
def update_note(note_id: str):
    db = read_db()
    note = next((n for n in db["notes"] if n.get("id") == note_id), None)
    if not note:
        abort(404)
    # Las notas de Mi espacio son privadas: solo su propietario puede modificarlas.
    if note.get("ownerId") != g.user["id"]:
        abort(403)
    text = request.form.get("text", "").strip()
    if not text:
        flash("La nota no puede quedar vacía.", "error")
        return redirect(url_for("space_page"))
    note["text"] = text[:4000]
    note["updatedAt"] = now_iso()
    write_db(db)
    flash("Nota actualizada.", "success")
    return redirect(url_for("space_page"))


@app.post("/notes/<note_id>/delete")
@login_required
def delete_note(note_id: str):
    db = read_db()
    before = len(db["notes"])
    db["notes"] = [n for n in db["notes"] if not (n.get("id") == note_id and n.get("ownerId") == g.user["id"])]
    if len(db["notes"]) == before:
        abort(404)
    write_db(db)
    flash("Nota eliminada.", "success")
    return redirect(url_for("space_page"))


# --------------------------- ATTENDANCE ---------------------------
def attendance_payload(db: dict[str, Any]):
    students = [u for u in db["users"] if role_of(u) == "participant" and u.get("status") == "active"]
    summary = []
    for u in students:
        recs = [r for r in db["attendanceRecords"] if r.get("userId") == u.get("id")]
        present = sum(1 for r in recs if r.get("status") == "present")
        absent = sum(1 for r in recs if r.get("status") == "absent")
        late = sum(1 for r in recs if r.get("status") == "late")
        excused = sum(1 for r in recs if r.get("status") == "excused")
        counted = present + absent + late
        rate = round(((present + late) / counted) * 100) if counted else 100
        summary.append({**safe_user(u), "userId": u["id"], "present": present, "absent": absent, "late": late, "excused": excused, "total": len(recs), "rate": rate, "blocked": absent >= BLOCK_AFTER_ABSENCES})
    sessions = []
    for s in db["attendanceSessions"]:
        event = next((e for e in db["events"] if e.get("id") == s.get("eventId")), None)
        module = get_module(db, s.get("moduleId"))
        sessions.append({**s, "eventTitle": event.get("title") if event else None, "moduleTitle": module.get("title") if module else None, "recordsCount": sum(1 for r in db["attendanceRecords"] if r.get("sessionId") == s.get("id"))})
    sessions.sort(key=lambda s: (s.get("date", ""), s.get("createdAt", "")), reverse=True)
    return students, summary, sessions


@app.route("/asistencia")
@roles_required("admin", "teacher")
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
    return render_template("attendance.html", sessions=sessions, summary=summary, students=students, selected=selected, record_map=record_map, official_events=official_events, modules=db["modules"], today=date.today().isoformat(), block_after=BLOCK_AFTER_ABSENCES)


@app.post("/attendance/sessions")
@roles_required("admin", "teacher")
def create_attendance_session():
    title = request.form.get("title", "").strip()
    session_date = request.form.get("date", "").strip()
    event_id = request.form.get("eventId") or None
    module_id = request.form.get("moduleId") or None
    try:
        week_number = int(request.form.get("weekNumber") or 0)
    except ValueError:
        week_number = 0
    db = read_db()
    if not title or not session_date or week_number < 1 or week_number > PROGRAM_WEEKS:
        flash("Nombre, fecha y semana (1 a 12) son obligatorios.", "error")
        return redirect(url_for("attendance_page"))
    if event_id and not any(e.get("id") == event_id and e.get("type") == "official" for e in db["events"]):
        flash("Actividad relacionada inválida.", "error")
        return redirect(url_for("attendance_page"))
    module = get_module(db, module_id) if module_id else None
    if module and not (int(module.get("startWeek", 1)) <= week_number <= int(module.get("endWeek", 12))):
        flash(f"{module['title']} corresponde a semanas {module['startWeek']}–{module['endWeek']}.", "error")
        return redirect(url_for("attendance_page"))
    item = {
        "id": new_id(), "title": title[:160], "date": session_date, "eventId": event_id, "moduleId": module_id,
        "weekNumber": week_number, "createdBy": g.user["id"], "createdAt": now_iso(), "updatedAt": now_iso(),
    }
    db["attendanceSessions"].append(item)
    write_db(db)
    flash("Lista creada. Ya puedes pasar asistencia.", "success")
    return redirect(url_for("attendance_page", session=item["id"]))


@app.post("/attendance/sessions/<session_id>/records")
@roles_required("admin", "teacher")
def save_attendance_records(session_id: str):
    db = read_db()
    attendance_session = next((s for s in db["attendanceSessions"] if s.get("id") == session_id), None)
    if not attendance_session:
        abort(404)
    allowed_ids = {u["id"] for u in db["users"] if role_of(u) == "participant" and u.get("status") == "active"}
    newly_blocked = []
    previous_absences = {uid: absence_count(db, uid) for uid in allowed_ids}
    for user_id in allowed_ids:
        status = request.form.get(f"status_{user_id}", "present")
        note = request.form.get(f"note_{user_id}", "").strip()[:500]
        if status not in ATTENDANCE_STATUSES:
            status = "present"
        index = next((i for i, r in enumerate(db["attendanceRecords"]) if r.get("sessionId") == session_id and r.get("userId") == user_id), -1)
        old = db["attendanceRecords"][index] if index >= 0 else None
        record = {
            "id": old.get("id") if old else new_id(), "sessionId": session_id, "userId": user_id,
            "status": status, "note": note, "takenBy": g.user["id"],
            "createdAt": old.get("createdAt") if old else now_iso(), "updatedAt": now_iso(),
        }
        if index >= 0:
            db["attendanceRecords"][index] = record
        else:
            db["attendanceRecords"].append(record)
    attendance_session["updatedAt"] = now_iso()
    for uid in allowed_ids:
        new_count = absence_count(db, uid)
        if previous_absences.get(uid, 0) < BLOCK_AFTER_ABSENCES <= new_count:
            newly_blocked.append(uid)
            db["notifications"].append({
                "id": new_id(), "userId": uid, "title": "Acceso bloqueado por inasistencias",
                "message": f"Acumulaste {new_count} faltas. El reglamento de 12 semanas bloquea la plataforma a partir de 3 faltas.",
                "read": False, "createdAt": now_iso(),
            })
    write_db(db)
    if newly_blocked:
        flash(f"Lista guardada. {len(newly_blocked)} alumno(s) alcanzaron 3 faltas y quedaron bloqueados automáticamente.", "success")
    else:
        flash("Lista de asistencia guardada.", "success")
    return redirect(url_for("attendance_page", session=session_id))


# --------------------------- ADMINISTRATION ---------------------------
@app.route("/admin")
@roles_required("admin")
def admin_page():
    db = read_db()
    users = [safe_user(u) for u in db["users"]]
    students = sorted([u for u in users if u.get("role") == "participant"], key=lambda u: u.get("name", "").lower())
    teachers = sorted([u for u in users if u.get("role") == "teacher"], key=lambda u: u.get("name", "").lower())
    admins = sorted([u for u in users if u.get("role") == "admin"], key=lambda u: u.get("name", "").lower())
    attendance_map = {u["id"]: absence_count(db, u["id"]) for u in students}
    stats = {
        "students": len(students), "teachers": len(teachers), "admins": len(admins),
        "blocked": sum(1 for u in students if attendance_map.get(u["id"], 0) >= BLOCK_AFTER_ABSENCES),
    }
    return render_template("admin.html", students=students, teachers=teachers, admins=admins, stats=stats, attendance_map=attendance_map, block_after=BLOCK_AFTER_ABSENCES)


@app.post("/users")
@roles_required("admin")
def create_user():
    db = read_db()
    email = request.form.get("email", "").strip().lower()
    name = request.form.get("name", "").strip()
    role = canonical_role(request.form.get("role", "participant"))
    if role not in ROLES:
        role = "participant"
    if not email or not name:
        flash("Nombre y correo son obligatorios.", "error")
        return redirect(url_for("admin_page"))
    if any(u.get("email", "").lower() == email for u in db["users"]):
        flash("Ese correo ya está registrado.", "error")
        return redirect(url_for("admin_page"))
    db["users"].append({
        "id": new_id(), "name": name[:100], "lastName": request.form.get("lastName", "").strip()[:120],
        "email": email, "passwordHash": hash_password(request.form.get("password") or "Temporal2026!"),
        "role": role, "status": "active", "theme": "light", "createdAt": now_iso(), "updatedAt": now_iso(),
    })
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
    role = canonical_role(request.form.get("role", user.get("role", "participant")))
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


# --------------------------- NOTIFICATIONS / SEARCH ---------------------------
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
    results = {"events": [], "tasks": [], "materials": [], "modules": []}
    if q:
        results["events"] = [e for e in db["events"] if (e.get("type") == "official" or e.get("ownerId") == uid) and q in f"{e.get('title','')} {e.get('description','')}".lower()][:12]
        results["tasks"] = [t for t in db["tasks"] if (t.get("ownerId") == uid or t.get("assignedTo") == uid) and q in f"{t.get('title','')} {t.get('description','')}".lower()][:12]
        results["materials"] = [m for m in db["materials"] if q in f"{m.get('name','')} {m.get('description','')}".lower()][:12]
        results["modules"] = [m for m in db["modules"] if q in f"{m.get('title','')} {m.get('description','')}".lower()][:12]
    return render_template("search.html", q=q, results=results)


if __name__ == "__main__":
    ensure_seed()
    print("+Q1LÍDER Flask Campus listo en http://localhost:5000")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
else:
    ensure_seed()
