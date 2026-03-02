import redis
from django.conf import settings


def get_redis_client() -> redis.Redis:
    return redis.Redis(
        host=settings.REDIS_HOST,
        port=int(settings.REDIS_PORT),
        db=int(getattr(settings, "REDIS_DB", 0)),
        password=settings.REDIS_PASSWORD or None,
        decode_responses=True,
    )
