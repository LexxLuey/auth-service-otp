from django.utils import timezone

from apps.accounts.models import User


def get_or_create_active_user(email: str) -> User:
    user, created = User.objects.get_or_create(email=email)

    update_fields = []
    if not user.is_active:
        user.is_active = True
        update_fields.append("is_active")

    user.last_login = timezone.now()
    update_fields.append("last_login")

    if not created:
        user.save(update_fields=update_fields)
    else:
        user.save()

    return user
