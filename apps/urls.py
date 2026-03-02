"""
Base URL configuration for all apps.
This file aggregates URLs from individual apps and will be included in the main config/urls.py
"""

from django.urls import include, path
from . import views

urlpatterns = [
    # API root (JSON)
    path("", views.api_root_view, name="api-root"),
    # Health check
    path("health", views.health_check_view, name="health-check"),
    # Accounts app URLs
    path("auth/", include("apps.accounts.urls")),
    # Audit app URLs
    path("audit/", include("apps.audit.urls")),
]
