import logging

from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.serializers import (
    InvalidOTPError,
    OTPRequestSerializer,
    RateLimitExceeded,
    OTPTemporarilyLocked,
    OTPVerifySerializer,
)
from apps.accounts.services import (
    RedisUnavailableError,
    consume_otp,
    generate_tokens_for_user,
    get_failed_attempts_ttl,
    get_or_create_active_user,
    increment_failed_attempt,
    reset_failed_attempts,
    set_lock,
    set_otp,
)
from apps.accounts.tasks import send_otp_email
from apps.audit.models import AuditEvent
from apps.audit.tasks import write_audit_log

logger = logging.getLogger(__name__)


class OTPRequestView(APIView):
    permission_classes = [AllowAny]
    otp_ttl_seconds = 300

    @staticmethod
    def _get_client_ip(request):
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "0.0.0.0")

    @extend_schema(
        summary="Request OTP",
        description="Generate and send a 6-digit OTP to the provided email address.",
        request=OTPRequestSerializer,
        responses={
            202: OpenApiResponse(
                description="OTP accepted and queued for delivery",
                response={
                    "type": "object",
                    "properties": {
                        "detail": {"type": "string"},
                        "expires_in": {"type": "integer"},
                    },
                    "required": ["detail", "expires_in"],
                },
            ),
            400: OpenApiResponse(description="Validation error"),
            429: OpenApiResponse(description="Rate limit exceeded"),
            503: OpenApiResponse(description="Service temporarily unavailable"),
        },
        examples=[
            OpenApiExample(
                "Request body",
                value={"email": "user@example.com"},
                request_only=True,
            ),
            OpenApiExample(
                "Success",
                value={"detail": "OTP sent", "expires_in": 300},
                response_only=True,
                status_codes=["202"],
            ),
            OpenApiExample(
                "Rate limited",
                value={
                    "detail": "Rate limit exceeded",
                    "limit_type": "email",
                    "retry_after": 120,
                },
                response_only=True,
                status_codes=["429"],
            ),
            OpenApiExample(
                "Redis down",
                value={"detail": "Service temporarily unavailable"},
                response_only=True,
                status_codes=["503"],
            ),
        ],
    )
    def post(self, request):
        ip_address = self._get_client_ip(request)
        serializer = OTPRequestSerializer(
            data=request.data, context={"ip_address": ip_address}
        )
        try:
            serializer.is_valid(raise_exception=True)
        except RateLimitExceeded as exc:
            return Response(
                {
                    "detail": "Rate limit exceeded",
                    "limit_type": str(exc.detail.get("limit_type", "")),
                    "retry_after": int(exc.detail.get("retry_after", 0)),
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        except RedisUnavailableError:
            return Response(
                {"detail": "Service temporarily unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        email = serializer.validated_data["email"]
        otp = serializer.generate_otp()
        user_agent = request.META.get("HTTP_USER_AGENT", "")

        try:
            set_otp(email=email, otp=otp, ttl_seconds=self.otp_ttl_seconds)
            send_otp_email.delay(email=email, otp=otp)
            write_audit_log.delay(
                event=AuditEvent.OTP_REQUESTED,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                metadata={"source": "otp_request"},
            )
        except RedisUnavailableError:
            return Response(
                {"detail": "Service temporarily unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except Exception:
            return Response(
                {"detail": "Service temporarily unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            {"detail": "OTP sent", "expires_in": self.otp_ttl_seconds},
            status=status.HTTP_202_ACCEPTED,
        )


class OTPVerifyView(APIView):
    permission_classes = [AllowAny]
    max_attempts = 5
    failed_window_seconds = 900
    lock_ttl_seconds = 900

    @staticmethod
    def _get_client_ip(request):
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "0.0.0.0")

    @staticmethod
    def _enqueue_audit_safe(**kwargs):
        try:
            write_audit_log.delay(**kwargs)
        except Exception as exc:
            logger.warning("Failed to enqueue audit log: %s", exc)

    @extend_schema(
        summary="Verify OTP",
        description="Validate OTP and issue JWT tokens for the user on success.",
        request=OTPVerifySerializer,
        responses={
            200: OpenApiResponse(
                description="OTP verified and JWT tokens issued",
                response={
                    "type": "object",
                    "properties": {
                        "access": {"type": "string"},
                        "refresh": {"type": "string"},
                    },
                    "required": ["access", "refresh"],
                },
            ),
            400: OpenApiResponse(description="Invalid OTP or validation error"),
            423: OpenApiResponse(description="Account temporarily locked"),
            503: OpenApiResponse(description="Service temporarily unavailable"),
        },
        examples=[
            OpenApiExample(
                "Request body",
                value={"email": "user@example.com", "otp": "123456"},
                request_only=True,
            ),
            OpenApiExample(
                "Success",
                value={"access": "<jwt_access>", "refresh": "<jwt_refresh>"},
                response_only=True,
                status_codes=["200"],
            ),
            OpenApiExample(
                "Invalid OTP",
                value={
                    "detail": "Invalid OTP",
                    "attempts_remaining": 4,
                    "retry_after": 840,
                },
                response_only=True,
                status_codes=["400"],
            ),
            OpenApiExample(
                "Locked",
                value={"detail": "Account temporarily locked", "retry_after": 900},
                response_only=True,
                status_codes=["423"],
            ),
            OpenApiExample(
                "Redis down",
                value={"detail": "Service temporarily unavailable"},
                response_only=True,
                status_codes=["503"],
            ),
        ],
    )
    def post(self, request):
        ip_address = self._get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")

        serializer = OTPVerifySerializer(
            data=request.data, context={"ip_address": ip_address}
        )
        try:
            serializer.is_valid(raise_exception=True)
        except InvalidOTPError as exc:
            email = request.data.get("email", "").strip().lower()
            detail = exc.detail
            self._enqueue_audit_safe(
                event=AuditEvent.OTP_FAILED,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                metadata={
                    "attempts_remaining": detail.get("attempts_remaining", 0),
                    "retry_after": detail.get("retry_after", 0),
                },
            )
            return Response(
                {
                    "detail": "Invalid OTP",
                    "attempts_remaining": int(detail.get("attempts_remaining", 0)),
                    "retry_after": int(detail.get("retry_after", 0)),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except OTPTemporarilyLocked as exc:
            email = request.data.get("email", "").strip().lower()
            detail = exc.detail
            self._enqueue_audit_safe(
                event=AuditEvent.OTP_LOCKED,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                metadata={"retry_after": detail.get("retry_after", 0)},
            )
            return Response(
                {
                    "detail": "Account temporarily locked",
                    "retry_after": int(detail.get("retry_after", 0)),
                },
                status=status.HTTP_423_LOCKED,
            )
        except RedisUnavailableError:
            return Response(
                {"detail": "Service temporarily unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        email = serializer.validated_data["email"]
        otp = serializer.validated_data["otp"]

        try:
            consumed_otp = consume_otp(email)
            if consumed_otp != otp:
                attempts = increment_failed_attempt(
                    email, window=self.failed_window_seconds
                )
                if attempts >= self.max_attempts:
                    set_lock(email, ttl=self.lock_ttl_seconds)
                    self._enqueue_audit_safe(
                        event=AuditEvent.OTP_LOCKED,
                        email=email,
                        ip_address=ip_address,
                        user_agent=user_agent,
                        metadata={"retry_after": self.lock_ttl_seconds},
                    )
                    return Response(
                        {
                            "detail": "Account temporarily locked",
                            "retry_after": self.lock_ttl_seconds,
                        },
                        status=status.HTTP_423_LOCKED,
                    )

                retry_after = get_failed_attempts_ttl(email)
                attempts_remaining = self.max_attempts - attempts
                self._enqueue_audit_safe(
                    event=AuditEvent.OTP_FAILED,
                    email=email,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    metadata={
                        "attempts_remaining": attempts_remaining,
                        "retry_after": retry_after,
                    },
                )
                return Response(
                    {
                        "detail": "Invalid OTP",
                        "attempts_remaining": attempts_remaining,
                        "retry_after": retry_after,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            reset_failed_attempts(email)
            user = get_or_create_active_user(email)
            tokens = generate_tokens_for_user(user)

            self._enqueue_audit_safe(
                event=AuditEvent.OTP_VERIFIED,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                metadata={"source": "otp_verify"},
            )
            return Response(tokens, status=status.HTTP_200_OK)
        except RedisUnavailableError:
            return Response(
                {"detail": "Service temporarily unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
