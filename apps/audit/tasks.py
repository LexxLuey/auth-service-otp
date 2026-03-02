from celery import shared_task

from apps.audit.models import AuditLog


@shared_task
def write_audit_log(
    event: str,
    email: str,
    ip_address: str | None = None,
    user_agent: str = "",
    metadata: dict | None = None,
):
    AuditLog.objects.create(
        event=event,
        email=email,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata=metadata or {},
    )
