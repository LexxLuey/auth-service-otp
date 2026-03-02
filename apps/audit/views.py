from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
)
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.filters import OrderingFilter
from rest_framework.permissions import IsAuthenticated

from apps.audit.filters import AuditLogFilter
from apps.audit.models import AuditLog
from apps.audit.serializers import AuditLogSerializer


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AuditLog.objects.all()
    serializer_class = AuditLogSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "head", "options"]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = AuditLogFilter
    ordering_fields = ["created_at"]
    ordering = ["-created_at"]

    @extend_schema(
        summary="List audit logs",
        description=(
            "Returns paginated audit log entries. "
            "Requires JWT Bearer authentication."
        ),
        parameters=[
            OpenApiParameter(
                name="email",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Filter by exact email",
            ),
            OpenApiParameter(
                name="event",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Filter by exact event (OTP_REQUESTED, OTP_VERIFIED, OTP_FAILED, OTP_LOCKED)",
            ),
            OpenApiParameter(
                name="from_date",
                type=str,
                location=OpenApiParameter.QUERY,
                description="ISO datetime lower bound for created_at (inclusive)",
            ),
            OpenApiParameter(
                name="to_date",
                type=str,
                location=OpenApiParameter.QUERY,
                description="ISO datetime upper bound for created_at (inclusive)",
            ),
            OpenApiParameter(
                name="ordering",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Ordering by created_at: created_at or -created_at",
            ),
            OpenApiParameter(
                name="page",
                type=int,
                location=OpenApiParameter.QUERY,
                description="Page number",
            ),
        ],
        responses={
            200: OpenApiResponse(
                description="Paginated audit logs list",
                response=AuditLogSerializer(many=True),
            ),
            401: OpenApiResponse(
                description="Authentication credentials were not provided"
            ),
        },
        examples=[
            OpenApiExample(
                "Filter by email and event",
                value={"email": "user@example.com", "event": "OTP_VERIFIED"},
                description="Example query parameters for email and event filters",
            ),
            OpenApiExample(
                "Filter by date range",
                value={
                    "from_date": "2026-03-02T00:00:00Z",
                    "to_date": "2026-03-02T23:59:59Z",
                },
                description="Example query parameters for ISO datetime range filters",
            ),
            OpenApiExample(
                "Paginated response",
                value={
                    "count": 2,
                    "next": None,
                    "previous": None,
                    "results": [
                        {
                            "id": 2,
                            "event": "OTP_VERIFIED",
                            "email": "user@example.com",
                            "ip_address": "127.0.0.1",
                            "user_agent": "test-agent",
                            "metadata": {"source": "otp_verify"},
                            "created_at": "2026-03-02T10:31:00Z",
                        },
                        {
                            "id": 1,
                            "event": "OTP_REQUESTED",
                            "email": "user@example.com",
                            "ip_address": "127.0.0.1",
                            "user_agent": "test-agent",
                            "metadata": {"source": "otp_request"},
                            "created_at": "2026-03-02T10:30:00Z",
                        },
                    ],
                },
                response_only=True,
                status_codes=["200"],
            ),
        ],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
