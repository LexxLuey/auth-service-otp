"""
URL configuration for audit app.
"""

from django.urls import path
from apps.audit.views import AuditLogViewSet

urlpatterns = [
    path("logs", AuditLogViewSet.as_view({"get": "list"}), name="audit-logs"),
]
