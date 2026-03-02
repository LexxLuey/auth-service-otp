from rest_framework_simplejwt.tokens import RefreshToken


def generate_tokens_for_user(user) -> dict:
    refresh = RefreshToken.for_user(user)
    refresh["email"] = user.email
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    }
