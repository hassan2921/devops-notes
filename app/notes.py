"""Notes: dashboard (search, filter, sort, pages, stats), create, edit, pin, delete, JSON API."""
from flask import (Blueprint, abort, current_app, flash, g, jsonify, redirect,
                   render_template, request, url_for)

from auth import login_required
from cache import cache
from db import get_cursor

bp = Blueprint("notes", __name__)

CATEGORIES = ["Work", "Study", "Personal", "Other"]
PRIORITIES = ["High", "Medium", "Low"]
SORTS = {
    "newest":   "pinned DESC, created_at DESC",
    "oldest":   "pinned DESC, created_at ASC",
    "priority": "pinned DESC, CASE priority WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END, created_at DESC",
    "title":    "pinned DESC, LOWER(title) ASC",
}


def read_note_form():
    """Read + validate the note form. Returns (data, errors)."""
    data = {
        "title": request.form.get("title", "").strip(),
        "content": request.form.get("content", "").strip(),
        "category": request.form.get("category", "Other"),
        "priority": request.form.get("priority", "Medium"),
    }
    errors = []
    if not data["title"]:
        errors.append("Title is required.")
    elif len(data["title"]) > 100:
        errors.append("Title must be 100 characters or fewer.")
    if len(data["content"]) > 2000:
        errors.append("Content must be 2000 characters or fewer.")
    if data["category"] not in CATEGORIES:
        errors.append("Choose a valid category.")
    if data["priority"] not in PRIORITIES:
        errors.append("Choose a valid priority.")
    return data, errors


def get_own_note(note_id):
    """Fetch a note ONLY if it belongs to the logged-in user, else 404."""
    with get_cursor() as cur:
        cur.execute("SELECT * FROM notes WHERE id = %s AND user_id = %s", (note_id, g.user["id"]))
        note = cur.fetchone()
    if note is None:
        abort(404)          # 404 (not 403) so users can't even tell the note exists
    return note


def count_visit():
    try:
        return cache.incr("notes:page_visits")
    except Exception:  # noqa: BLE001
        return "unavailable"


@bp.route("/")
@login_required
def index():
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "")
    sort = request.args.get("sort", "newest")
    if sort not in SORTS:
        sort = "newest"
    page = max(1, request.args.get("page", 1, type=int))
    per_page = current_app.config["NOTES_PER_PAGE"]

    # Build the WHERE clause from the filters. Values always go in as %s parameters
    # (never pasted into the SQL string), which prevents SQL injection.
    where, params = ["user_id = %s"], [g.user["id"]]
    if q:
        where.append("(title ILIKE %s OR content ILIKE %s)")
        params += [f"%{q}%", f"%{q}%"]
    if category in CATEGORIES:
        where.append("category = %s")
        params.append(category)
    where_sql = " AND ".join(where)

    with get_cursor() as cur:
        cur.execute(f"SELECT COUNT(*) AS n FROM notes WHERE {where_sql}", params)
        total = cur.fetchone()["n"]
        pages = max(1, -(-total // per_page))          # ceiling division
        page = min(page, pages)

        cur.execute(
            f"SELECT * FROM notes WHERE {where_sql} ORDER BY {SORTS[sort]} LIMIT %s OFFSET %s",
            params + [per_page, (page - 1) * per_page],
        )
        notes = cur.fetchall()

        # Dashboard stats for this user
        cur.execute(
            """SELECT COUNT(*) AS total,
                      COUNT(*) FILTER (WHERE pinned)            AS pinned,
                      COUNT(*) FILTER (WHERE priority = 'High') AS high
               FROM notes WHERE user_id = %s""",
            (g.user["id"],),
        )
        stats = cur.fetchone()
        cur.execute(
            "SELECT category, COUNT(*) AS n FROM notes WHERE user_id = %s GROUP BY category",
            (g.user["id"],),
        )
        per_category = {row["category"]: row["n"] for row in cur.fetchall()}

    return render_template(
        "index.html",
        notes=notes, total=total, page=page, pages=pages,
        q=q, category=category, sort=sort,
        stats=stats, per_category=per_category,
        categories=CATEGORIES, priorities=PRIORITIES, sorts=SORTS.keys(),
        visits=count_visit(),
    )


@bp.route("/notes", methods=["POST"])
@login_required
def create():
    data, errors = read_note_form()
    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("notes.index"))
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO notes (user_id, title, content, category, priority)
               VALUES (%s, %s, %s, %s, %s)""",
            (g.user["id"], data["title"], data["content"], data["category"], data["priority"]),
        )
    flash("Note added.", "success")
    return redirect(url_for("notes.index"))


@bp.route("/notes/<int:note_id>/edit", methods=["GET", "POST"])
@login_required
def edit(note_id):
    note = get_own_note(note_id)
    if request.method == "POST":
        data, errors = read_note_form()
        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("edit.html", note={**note, **data},
                                   categories=CATEGORIES, priorities=PRIORITIES), 400
        with get_cursor() as cur:
            cur.execute(
                """UPDATE notes SET title = %s, content = %s, category = %s, priority = %s,
                          updated_at = NOW()
                   WHERE id = %s AND user_id = %s""",
                (data["title"], data["content"], data["category"], data["priority"],
                 note_id, g.user["id"]),
            )
        flash("Note updated.", "success")
        return redirect(url_for("notes.index"))
    return render_template("edit.html", note=note, categories=CATEGORIES, priorities=PRIORITIES)


@bp.route("/notes/<int:note_id>/pin", methods=["POST"])
@login_required
def toggle_pin(note_id):
    get_own_note(note_id)
    with get_cursor() as cur:
        cur.execute(
            "UPDATE notes SET pinned = NOT pinned WHERE id = %s AND user_id = %s RETURNING pinned",
            (note_id, g.user["id"]),
        )
        pinned = cur.fetchone()["pinned"]
    flash("Note pinned." if pinned else "Note unpinned.", "success")
    return redirect(request.referrer or url_for("notes.index"))


@bp.route("/notes/<int:note_id>/delete", methods=["POST"])
@login_required
def delete(note_id):
    get_own_note(note_id)
    with get_cursor() as cur:
        cur.execute("DELETE FROM notes WHERE id = %s AND user_id = %s", (note_id, g.user["id"]))
    flash("Note deleted.", "success")
    return redirect(url_for("notes.index"))


@bp.route("/api/notes")
def api_notes():
    """JSON API: the logged-in user's notes (optional ?category=Work)."""
    if g.user is None:
        return jsonify(error="login required"), 401
    params = [g.user["id"]]
    sql = "SELECT id, title, content, category, priority, pinned, created_at, updated_at FROM notes WHERE user_id = %s"
    category = request.args.get("category")
    if category in CATEGORIES:
        sql += " AND category = %s"
        params.append(category)
    with get_cursor() as cur:
        cur.execute(sql + " ORDER BY " + SORTS["newest"], params)
        rows = cur.fetchall()
    for r in rows:
        r["created_at"] = r["created_at"].isoformat()
        r["updated_at"] = r["updated_at"].isoformat() if r["updated_at"] else None
    return jsonify(user=g.user["username"], count=len(rows), notes=rows)
