from django.db import models


class AuditEvent(models.TextChoices):
    OTP_REQUESTED = "OTP_REQUESTED", "OTP requested"
    OTP_VERIFIED = "OTP_VERIFIED", "OTP verified"
    OTP_FAILED = "OTP_FAILED", "OTP failed"
    OTP_LOCKED = "OTP_LOCKED", "OTP locked"


class AuditLog(models.Model):
    event = models.CharField(max_length=32, choices=AuditEvent.choices, db_index=True)
    email = models.EmailField(max_length=255, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["event", "created_at"])]

    def __str__(self):
        return f"{self.event} - {self.email}"
