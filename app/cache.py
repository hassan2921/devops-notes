"""Redis clients. 'redis' resolves to the Redis container through Docker DNS."""
import redis

from config import Config

# For our own keys (visit counter, failed-login counters): returns str
cache = redis.Redis(
    host=Config.REDIS_HOST, port=Config.REDIS_PORT,
    socket_connect_timeout=2, decode_responses=True,
)

# For Flask-Session, which stores sessions as bytes
session_store = redis.Redis(
    host=Config.REDIS_HOST, port=Config.REDIS_PORT, socket_connect_timeout=2,
)
