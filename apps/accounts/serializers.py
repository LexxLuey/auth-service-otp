import secrets

from rest_framework import serializers, status
from rest_framework.exceptions import APIException

from apps.accounts.services import (
    RedisUnavailableError,
    check_email_limit,
    check_ip_limit,
    get_failed_attempts_ttl,
    get_otp,
    increment_failed_attempt,
    is_locked,
    set_lock,
)


class RateLimitExceeded(APIException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_detail = "Rate limit exceeded."
    default_code = "rate_limited"

    def __init__(self, *, limit_type: str, retry_after: int):
        super().__init__(
            detail={
                "detail": "Rate limit exceeded",
                "limit_type": limit_type,
                "retry_after": max(int(retry_after), 0),
            }
        )


class OTPRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)

    def validate_email(self, value):
        return value.strip().lower()

    def validate(self, attrs):
        email = attrs["email"]
        ip_address = self.context.get("ip_address", "0.0.0.0")

        try:
            allowed, retry_after = check_email_limit(email=email, limit=3, window=600)
            if not allowed:
                raise RateLimitExceeded(limit_type="email", retry_after=retry_after)

            allowed, retry_after = check_ip_limit(ip=ip_address, limit=10, window=3600)
            if not allowed:
                raise RateLimitExceeded(limit_type="ip", retry_after=retry_after)
        except RedisUnavailableError:
            raise

        return attrs

    @staticmethod
    def generate_otp() -> str:
        return f"{secrets.randbelow(1_000_000):06d}"


class InvalidOTPError(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Invalid OTP."
    default_code = "invalid_otp"

    def __init__(self, *, attempts_remaining: int, retry_after: int):
        super().__init__(
            detail={
                "detail": "Invalid OTP",
                "attempts_remaining": max(int(attempts_remaining), 0),
                "retry_after": max(int(retry_after), 0),
            }
        )


class OTPTemporarilyLocked(APIException):
    status_code = status.HTTP_423_LOCKED
    default_detail = "Account temporarily locked."
    default_code = "otp_locked"

    def __init__(self, *, retry_after: int):
        super().__init__(
            detail={
                "detail": "Account temporarily locked",
                "retry_after": max(int(retry_after), 0),
            }
        )


class OTPVerifySerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    otp = serializers.RegexField(regex=r"^\d{6}$", required=True)

    max_attempts = 5
    failed_window_seconds = 900
    lock_ttl_seconds = 900

    def validate_email(self, value):
        return value.strip().lower()

    def validate(self, attrs):
        email = attrs["email"]
        otp = attrs["otp"]

        locked, lock_ttl = is_locked(email)
        if locked:
            raise OTPTemporarilyLocked(retry_after=lock_ttl)

        saved_otp = get_otp(email)
        if saved_otp != otp:
            attempts = increment_failed_attempt(
                email, window=self.failed_window_seconds
            )
            if attempts >= self.max_attempts:
                set_lock(email, ttl=self.lock_ttl_seconds)
                raise OTPTemporarilyLocked(retry_after=self.lock_ttl_seconds)

            retry_after = get_failed_attempts_ttl(email)
            raise InvalidOTPError(
                attempts_remaining=self.max_attempts - attempts,
                retry_after=retry_after,
            )

        return attrs
