import redis

from .rate_limit import RedisUnavailableError
from .redis_client import get_redis_client
from .redis_keys import otp_key


def set_otp_if_absent(email: str, otp: str, ttl_seconds: int = 300) -> bool:
    try:
        client = get_redis_client()
        return bool(client.set(otp_key(email), otp, ex=ttl_seconds, nx=True))
    except redis.RedisError as exc:
        raise RedisUnavailableError("Redis is unavailable") from exc


def set_otp(email: str, otp: str, ttl_seconds: int = 300) -> bool:
    try:
        client = get_redis_client()
        return bool(client.set(otp_key(email), otp, ex=ttl_seconds))
    except redis.RedisError as exc:
        raise RedisUnavailableError("Redis is unavailable") from exc


def get_otp(email: str):
    try:
        client = get_redis_client()
        return client.get(otp_key(email))
    except redis.RedisError as exc:
        raise RedisUnavailableError("Redis is unavailable") from exc


def consume_otp(email: str):
    try:
        client = get_redis_client()
        key = otp_key(email)

        if hasattr(client, "getdel"):
            return client.getdel(key)

        pipe = client.pipeline(transaction=True)
        pipe.get(key)
        pipe.delete(key)
        value, _ = pipe.execute()
        return value
    except redis.RedisError as exc:
        raise RedisUnavailableError("Redis is unavailable") from exc


def get_otp_ttl(email: str) -> int:
    try:
        client = get_redis_client()
        return int(client.ttl(otp_key(email)))
    except redis.RedisError as exc:
        raise RedisUnavailableError("Redis is unavailable") from exc
