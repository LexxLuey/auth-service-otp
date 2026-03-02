import django_filters

from apps.audit.models import AuditEvent, AuditLog


class AuditLogFilter(django_filters.FilterSet):
    email = django_filters.CharFilter(field_name="email", lookup_expr="exact")
    event = django_filters.ChoiceFilter(
        field_name="event", choices=AuditEvent.choices, lookup_expr="exact"
    )
    from_date = django_filters.IsoDateTimeFilter(
        field_name="created_at", lookup_expr="gte"
    )
    to_date = django_filters.IsoDateTimeFilter(
        field_name="created_at", lookup_expr="lte"
    )

    class Meta:
        model = AuditLog
        fields = ["email", "event", "from_date", "to_date"]
