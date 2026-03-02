from celery import shared_task


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def send_otp_email(self, email: str, otp: str):
    print(f"[OTP EMAIL] Send OTP {otp} to {email}")
