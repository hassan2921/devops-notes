"""PostgreSQL access: a connection pool and a safe cursor helper."""
import time
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool

_pool = None


def init_pool(db_config, retries=10, delay=3):
    """Create the pool, retrying while the database container starts up."""
    global _pool
    for attempt in range(1, retries + 1):
        try:
            _pool = ThreadedConnectionPool(minconn=1, maxconn=5, **db_config)
            return
        except psycopg2.OperationalError:
            print(f"DB not ready (attempt {attempt}/{retries}), retrying in {delay}s...")
            time.sleep(delay)
    raise RuntimeError("Could not connect to the database")


@contextmanager
def get_cursor():
    """
    Borrow a connection, give a cursor that returns rows as dicts,
    COMMIT on success, ROLLBACK on any error, always return the connection.
    """
    conn = _pool.getconn()
    broken = False
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            yield cur
        conn.commit()
    except psycopg2.OperationalError:
        broken = True                     # e.g. DB restarted: drop this connection
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn, close=broken or conn.closed != 0)


def init_schema(schema_path):
    """Create tables. The advisory lock stops Gunicorn workers racing each other."""
    with open(schema_path, encoding="utf-8") as f:
        sql = f.read()
    with get_cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(4242)")
        cur.execute(sql)
