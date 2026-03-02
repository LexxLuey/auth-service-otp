from django.contrib import admin
from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ["event", "email", "ip_address", "created_at"]
    list_filter = ["event", "created_at"]
    search_fields = ["email"]
    readonly_fields = ["created_at"]
