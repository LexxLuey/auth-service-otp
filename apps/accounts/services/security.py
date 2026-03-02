import redis

from .rate_limit import RedisUnavailableError
from .redis_client import get_redis_client
from .redis_keys import failed_attempts_key, lock_key


def increment_failed_attempt(email: str, window: int = 900) -> int:
    try:
        client = get_redis_client()
        key = failed_attempts_key(email)
        count = int(client.incr(key))
        if count == 1:
            client.expire(key, window)
        return count
    except redis.RedisError as exc:
        raise RedisUnavailableError("Redis is unavailable") from exc


def set_lock(email: str, ttl: int = 900):
    try:
        client = get_redis_client()
        client.set(lock_key(email), "1", ex=ttl)
    except redis.RedisError as exc:
        raise RedisUnavailableError("Redis is unavailable") from exc


def is_locked(email: str):
    try:
        client = get_redis_client()
        ttl = int(client.ttl(lock_key(email)))
        if ttl > 0:
            return True, ttl
        return False, 0
    except redis.RedisError as exc:
        raise RedisUnavailableError("Redis is unavailable") from exc


def get_failed_attempts_ttl(email: str) -> int:
    try:
        client = get_redis_client()
        ttl = int(client.ttl(failed_attempts_key(email)))
        return ttl if ttl > 0 else 0
    except redis.RedisError as exc:
        raise RedisUnavailableError("Redis is unavailable") from exc


def reset_failed_attempts(email: str):
    try:
        client = get_redis_client()
        client.delete(failed_attempts_key(email))
    except redis.RedisError as exc:
        raise RedisUnavailableError("Redis is unavailable") from exc
