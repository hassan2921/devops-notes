"""
Notes Manager: multi-user notes app.

Flask (back-end) + Jinja templates (front-end) + PostgreSQL (data) + Redis (sessions,
login lockout, visit counter). Runs under Gunicorn behind Nginx in Docker Compose.

Code layout:
  config.py  settings from environment variables
  db.py      PostgreSQL connection pool + cursor helper
  cache.py   Redis clients
  auth.py    register / login / logout blueprint
  notes.py   notes dashboard, CRUD, pin, JSON API blueprint
  app.py     creates the app, CSRF protection, /health, error pages
"""
import hmac
import os
import secrets
import socket

from flask import Flask, abort, render_template, request, session
from flask_session import Session

import db
from cache import cache, session_store
from config import Config


def get_csrf_token():
    """One random token per session; every form sends it back."""
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)
    return session["csrf_token"]


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.config["SESSION_REDIS"] = session_store
    Session(app)                                   # sessions live in Redis, not the cookie

    db.init_pool(Config.DB_CONFIG)
    db.init_schema(os.path.join(app.root_path, "schema.sql"))

    from auth import bp as auth_bp
    from notes import bp as notes_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(notes_bp)

    @app.before_request
    def csrf_protect():
        """Reject any POST whose form token doesn't match the session's token."""
        if request.method == "POST":
            expected = session.get("csrf_token")
            sent = request.form.get("csrf_token", "")
            if not expected or not hmac.compare_digest(expected, sent):
                abort(400, "Your form expired. Please go back and try again.")

    @app.context_processor
    def template_globals():
        return {"csrf_token": get_csrf_token, "served_by": socket.gethostname()}

    @app.route("/health")
    def health():
        """Used by the AWS Load Balancer health check (through Nginx)."""
        status, code = {"database": "ok", "redis": "ok", "served_by": socket.gethostname()}, 200
        try:
            with db.get_cursor() as cur:
                cur.execute("SELECT 1")
        except Exception:  # noqa: BLE001
            status["database"], code = "error", 500
        try:
            cache.ping()
        except Exception:  # noqa: BLE001
            status["redis"], code = "error", 500      # sessions need Redis
        return status, code

    @app.errorhandler(400)
    @app.errorhandler(404)
    @app.errorhandler(405)
    def http_error(err):
        return render_template("error.html", code=err.code,
                               message=err.description), err.code

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
