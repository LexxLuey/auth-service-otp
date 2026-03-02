def _normalize_email(email: str) -> str:
    return email.strip().lower()


def otp_key(email: str) -> str:
    return f"otp:{_normalize_email(email)}"


def email_rate_limit_key(email: str) -> str:
    return f"rate:email:{_normalize_email(email)}"


def ip_rate_limit_key(ip: str) -> str:
    return f"rate:ip:{ip}"


def failed_attempts_key(email: str) -> str:
    return f"failed:{_normalize_email(email)}"


def lock_key(email: str) -> str:
    return f"lock:{_normalize_email(email)}"
