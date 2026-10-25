"""Accounts: register, login (with lockout), logout, and the login_required guard."""
import re
from functools import wraps

import psycopg2
from flask import (Blueprint, current_app, flash, g, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from cache import cache
from db import get_cursor

bp = Blueprint("auth", __name__)

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,30}$")


@bp.before_app_request
def load_logged_in_user():
    """Runs before every request: puts the current user (or None) in g.user."""
    g.user = None
    user_id = session.get("user_id")
    if user_id is not None:
        with get_cursor() as cur:
            cur.execute("SELECT id, username FROM users WHERE id = %s", (user_id,))
            g.user = cur.fetchone()


def login_required(view):
    """Decorator: send visitors who aren't logged in to the login page."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            flash("Please log in to continue.", "error")
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def _start_session(user_id):
    session.clear()                 # new session on login (prevents session fixation)
    session["user_id"] = user_id
    session.permanent = True


def _safe_next(target):
    """Only allow redirects inside this site (blocks open-redirect attacks)."""
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return url_for("notes.index")


@bp.route("/register", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect(url_for("notes.index"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")

        errors = []
        if not USERNAME_RE.match(username):
            errors.append("Username must be 3-30 letters, numbers or underscores.")
        if len(password) < 6:
            errors.append("Password must be at least 6 characters.")
        if password != confirm:
            errors.append("Passwords do not match.")

        if not errors:
            try:
                with get_cursor() as cur:
                    cur.execute(
                        "INSERT INTO users (username, password_hash) VALUES (%s, %s) RETURNING id",
                        (username, generate_password_hash(password)),
                    )
                    user_id = cur.fetchone()["id"]
                _start_session(user_id)
                flash(f"Welcome, {username}! Your account is ready.", "success")
                return redirect(url_for("notes.index"))
            except psycopg2.errors.UniqueViolation:
                errors.append("That username is already taken.")

        for e in errors:
            flash(e, "error")
        return render_template("register.html", username=username), 400
    return render_template("register.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("notes.index"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        max_attempts = current_app.config["MAX_LOGIN_ATTEMPTS"]
        lockout = current_app.config["LOCKOUT_SECONDS"]
        fail_key = f"notes:login_fail:{username.lower()}"

        # Too many wrong passwords? (counter lives in Redis and expires by itself)
        if int(cache.get(fail_key) or 0) >= max_attempts:
            minutes = max(1, (cache.ttl(fail_key) + 59) // 60)
            flash(f"Too many failed attempts. Try again in {minutes} minute(s).", "error")
            return render_template("login.html", username=username), 429

        with get_cursor() as cur:
            cur.execute("SELECT id, password_hash FROM users WHERE username = %s", (username,))
            user = cur.fetchone()

        if user and check_password_hash(user["password_hash"], password):
            cache.delete(fail_key)
            _start_session(user["id"])
            flash(f"Logged in as {username}.", "success")
            return redirect(_safe_next(request.args.get("next")))

        attempts = cache.incr(fail_key)
        cache.expire(fail_key, lockout)
        left = max(0, max_attempts - attempts)
        # Same message for "no such user" and "wrong password" (don't reveal which)
        flash(f"Invalid username or password. {left} attempt(s) left.", "error")
        return render_template("login.html", username=username), 401
    return render_template("login.html")


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("auth.login"))
