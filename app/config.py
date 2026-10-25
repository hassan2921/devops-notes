"""All settings come from environment variables (set in .env / docker-compose.yml)."""
import os
from datetime import timedelta


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")

    DB_CONFIG = {
        "host": os.getenv("DB_HOST", "db"),            # Compose service name
        "port": int(os.getenv("DB_PORT", "5432")),
        "dbname": os.getenv("POSTGRES_DB", "notesdb"),
        "user": os.getenv("POSTGRES_USER", "notesuser"),
        "password": os.getenv("POSTGRES_PASSWORD", "notespass"),
    }

    REDIS_HOST = os.getenv("REDIS_HOST", "redis")      # Compose service name
    REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

    # Server-side sessions in Redis (Flask-Session)
    SESSION_TYPE = "redis"
    SESSION_PERMANENT = True
    SESSION_KEY_PREFIX = "notes:session:"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=2)
    SESSION_COOKIE_HTTPONLY = True        # JavaScript can't read the cookie
    SESSION_COOKIE_SAMESITE = "Lax"       # basic cross-site protection

    NOTES_PER_PAGE = 6
    MAX_LOGIN_ATTEMPTS = 5
    LOCKOUT_SECONDS = 300
