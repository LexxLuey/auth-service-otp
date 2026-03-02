import redis

from .redis_client import get_redis_client
from .redis_keys import email_rate_limit_key, ip_rate_limit_key


class RedisUnavailableError(RuntimeError):
    pass


def increment_with_window(key: str, window_seconds: int) -> int:
    try:
        client = get_redis_client()
        count = int(client.incr(key))
        if count == 1:
            client.expire(key, window_seconds)
        return count
    except redis.RedisError as exc:
        raise RedisUnavailableError("Redis is unavailable") from exc


def _key_ttl(key: str) -> int:
    try:
        client = get_redis_client()
        ttl = int(client.ttl(key))
        return ttl if ttl > 0 else 0
    except redis.RedisError as exc:
        raise RedisUnavailableError("Redis is unavailable") from exc


def check_email_limit(email: str, limit: int = 3, window: int = 600):
    key = email_rate_limit_key(email)
    count = increment_with_window(key, window)
    if count <= limit:
        return True, 0
    return False, _key_ttl(key)


def check_ip_limit(ip: str, limit: int = 10, window: int = 3600):
    key = ip_rate_limit_key(ip)
    count = increment_with_window(key, window)
    if count <= limit:
        return True, 0
    return False, _key_ttl(key)
