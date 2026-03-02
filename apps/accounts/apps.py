from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"  # This is important - it's the full Python path
    label = "accounts"  # Short name for Django internals
    verbose_name = "Accounts"
