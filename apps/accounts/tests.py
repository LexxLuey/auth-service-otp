import redis
from unittest.mock import patch

from django.conf import settings
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.accounts.serializers import (
    InvalidOTPError,
    OTPRequestSerializer,
    OTPTemporarilyLocked,
    OTPVerifySerializer,
    RateLimitExceeded,
)
from apps.accounts.services import otp_store, rate_limit, security
from apps.accounts.services.rate_limit import RedisUnavailableError


class FakePipeline:
    def __init__(self, client):
        self.client = client
        self.commands = []

    def get(self, key):
        self.commands.append(("get", key))
        return self

    def delete(self, key):
        self.commands.append(("delete", key))
        return self

    def execute(self):
        results = []
        for command, key in self.commands:
            if command == "get":
                results.append(self.client.get(key))
            elif command == "delete":
                results.append(self.client.delete(key))
        return results


class FakeRedis:
    def __init__(self):
        self.store = {}
        self.ttls = {}

    def set(self, key, value, ex=None, nx=False):
        if nx and key in self.store:
            return False
        self.store[key] = value
        if ex is not None:
            self.ttls[key] = int(ex)
        return True

    def get(self, key):
        return self.store.get(key)

    def getdel(self, key):
        value = self.store.get(key)
        self.delete(key)
        return value

    def delete(self, key):
        existed = 1 if key in self.store else 0
        self.store.pop(key, None)
        self.ttls.pop(key, None)
        return existed

    def ttl(self, key):
        return int(self.ttls.get(key, -2))

    def incr(self, key):
        current = int(self.store.get(key, 0)) + 1
        self.store[key] = str(current)
        return current

    def expire(self, key, seconds):
        if key in self.store:
            self.ttls[key] = int(seconds)
            return True
        return False

    def pipeline(self, transaction=True):
        return FakePipeline(self)


class FakeRedisNoGetDel(FakeRedis):
    def __getattribute__(self, name):
        if name == "getdel":
            raise AttributeError
        return super().__getattribute__(name)


class OTPStoreTests(SimpleTestCase):
    @patch("apps.accounts.services.otp_store.get_redis_client")
    def test_set_get_consume_otp(self, mock_client):
        fake = FakeRedis()
        mock_client.return_value = fake

        created = otp_store.set_otp_if_absent("User@Example.com", "123456")
        duplicate = otp_store.set_otp_if_absent("user@example.com", "222222")
        fetched = otp_store.get_otp("user@example.com")
        consumed = otp_store.consume_otp("user@example.com")
        after_consume = otp_store.get_otp("user@example.com")

        self.assertTrue(created)
        self.assertFalse(duplicate)
        self.assertEqual(fetched, "123456")
        self.assertEqual(consumed, "123456")
        self.assertIsNone(after_consume)

    @patch("apps.accounts.services.otp_store.get_redis_client")
    def test_set_otp_replaces_existing_value(self, mock_client):
        fake = FakeRedis()
        mock_client.return_value = fake

        otp_store.set_otp("user@example.com", "111111")
        otp_store.set_otp("user@example.com", "222222")

        self.assertEqual(otp_store.get_otp("user@example.com"), "222222")

    @patch("apps.accounts.services.otp_store.get_redis_client")
    def test_consume_otp_fallback_pipeline_when_getdel_unavailable(self, mock_client):
        fake = FakeRedisNoGetDel()
        mock_client.return_value = fake

        otp_store.set_otp("user@example.com", "123456")
        consumed = otp_store.consume_otp("user@example.com")
        after_consume = otp_store.get_otp("user@example.com")

        self.assertEqual(consumed, "123456")
        self.assertIsNone(after_consume)


class RateLimitServiceTests(SimpleTestCase):
    @patch("apps.accounts.services.rate_limit.get_redis_client")
    def test_email_rate_limit(self, mock_client):
        fake = FakeRedis()
        mock_client.return_value = fake

        self.assertEqual(
            rate_limit.check_email_limit("user@example.com", limit=2), (True, 0)
        )
        self.assertEqual(
            rate_limit.check_email_limit("user@example.com", limit=2), (True, 0)
        )
        allowed, retry_after = rate_limit.check_email_limit("user@example.com", limit=2)
        self.assertFalse(allowed)
        self.assertGreater(retry_after, 0)

    @patch("apps.accounts.services.rate_limit.get_redis_client")
    def test_redis_unavailable_raises_domain_error(self, mock_client):
        mock_client.side_effect = redis.RedisError("down")
        with self.assertRaises(RedisUnavailableError):
            rate_limit.check_email_limit("user@example.com")


class SecurityServiceTests(SimpleTestCase):
    @patch("apps.accounts.services.security.get_redis_client")
    def test_lock_and_failed_attempt_helpers(self, mock_client):
        fake = FakeRedis()
        mock_client.return_value = fake

        self.assertEqual(security.increment_failed_attempt("user@example.com"), 1)
        self.assertEqual(security.increment_failed_attempt("user@example.com"), 2)
        security.set_lock("user@example.com", ttl=900)

        locked, ttl = security.is_locked("user@example.com")
        self.assertTrue(locked)
        self.assertGreater(ttl, 0)

        security.reset_failed_attempts("user@example.com")
        self.assertEqual(fake.get("failed:user@example.com"), None)

    @patch("apps.accounts.services.security.get_redis_client")
    def test_get_failed_attempts_ttl_returns_zero_when_absent(self, mock_client):
        fake = FakeRedis()
        mock_client.return_value = fake
        self.assertEqual(security.get_failed_attempts_ttl("user@example.com"), 0)


class CeleryConfigTests(SimpleTestCase):
    def test_celery_app_imports(self):
        from config.celery import app

        self.assertIsNotNone(app)

    def test_celery_settings_exposed(self):
        self.assertTrue(hasattr(settings, "CELERY_TASK_ALWAYS_EAGER"))
        self.assertTrue(hasattr(settings, "CELERY_TASK_TIME_LIMIT"))
        self.assertTrue(hasattr(settings, "CELERY_TASK_SOFT_TIME_LIMIT"))


class OTPRequestSerializerTests(SimpleTestCase):
    @patch("apps.accounts.serializers.check_email_limit")
    @patch("apps.accounts.serializers.check_ip_limit")
    def test_valid_email_is_normalized(self, mock_check_ip, mock_check_email):
        mock_check_email.return_value = (True, 0)
        mock_check_ip.return_value = (True, 0)

        serializer = OTPRequestSerializer(
            data={"email": "User@Example.COM"},
            context={"ip_address": "127.0.0.1"},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["email"], "user@example.com")

    @patch("apps.accounts.serializers.check_email_limit")
    def test_email_rate_limit_raises_429(self, mock_check_email):
        mock_check_email.return_value = (False, 120)
        serializer = OTPRequestSerializer(
            data={"email": "user@example.com"},
            context={"ip_address": "127.0.0.1"},
        )
        with self.assertRaises(RateLimitExceeded):
            serializer.is_valid(raise_exception=True)

    @patch("apps.accounts.serializers.check_email_limit")
    @patch("apps.accounts.serializers.check_ip_limit")
    def test_ip_rate_limit_raises_429(self, mock_check_ip, mock_check_email):
        mock_check_email.return_value = (True, 0)
        mock_check_ip.return_value = (False, 200)
        serializer = OTPRequestSerializer(
            data={"email": "user@example.com"},
            context={"ip_address": "127.0.0.1"},
        )
        with self.assertRaises(RateLimitExceeded):
            serializer.is_valid(raise_exception=True)


class OTPVerifySerializerTests(SimpleTestCase):
    @patch("apps.accounts.serializers.get_otp")
    @patch("apps.accounts.serializers.is_locked")
    def test_verify_serializer_valid_when_otp_matches(
        self, mock_is_locked, mock_get_otp
    ):
        mock_is_locked.return_value = (False, 0)
        mock_get_otp.return_value = "123456"

        serializer = OTPVerifySerializer(
            data={"email": "User@Example.com", "otp": "123456"}
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["email"], "user@example.com")

    @patch("apps.accounts.serializers.is_locked")
    def test_verify_serializer_returns_locked(self, mock_is_locked):
        mock_is_locked.return_value = (True, 900)
        serializer = OTPVerifySerializer(
            data={"email": "user@example.com", "otp": "123456"}
        )
        with self.assertRaises(OTPTemporarilyLocked):
            serializer.is_valid(raise_exception=True)

    @patch("apps.accounts.serializers.get_failed_attempts_ttl")
    @patch("apps.accounts.serializers.increment_failed_attempt")
    @patch("apps.accounts.serializers.get_otp")
    @patch("apps.accounts.serializers.is_locked")
    def test_verify_serializer_invalid_otp_increments_attempts(
        self, mock_is_locked, mock_get_otp, mock_increment, mock_ttl
    ):
        mock_is_locked.return_value = (False, 0)
        mock_get_otp.return_value = "654321"
        mock_increment.return_value = 1
        mock_ttl.return_value = 850

        serializer = OTPVerifySerializer(
            data={"email": "user@example.com", "otp": "123456"}
        )
        with self.assertRaises(InvalidOTPError):
            serializer.is_valid(raise_exception=True)

    @patch("apps.accounts.serializers.set_lock")
    @patch("apps.accounts.serializers.increment_failed_attempt")
    @patch("apps.accounts.serializers.get_otp")
    @patch("apps.accounts.serializers.is_locked")
    def test_verify_serializer_locks_after_5th_failure(
        self, mock_is_locked, mock_get_otp, mock_increment, mock_set_lock
    ):
        mock_is_locked.return_value = (False, 0)
        mock_get_otp.return_value = "654321"
        mock_increment.return_value = 5

        serializer = OTPVerifySerializer(
            data={"email": "user@example.com", "otp": "123456"}
        )
        with self.assertRaises(OTPTemporarilyLocked):
            serializer.is_valid(raise_exception=True)
        mock_set_lock.assert_called_once()

    @patch("apps.accounts.serializers.get_otp")
    @patch("apps.accounts.serializers.is_locked")
    def test_verify_serializer_redis_unavailable(self, mock_is_locked, mock_get_otp):
        mock_is_locked.return_value = (False, 0)
        mock_get_otp.side_effect = RedisUnavailableError("Redis is unavailable")
        serializer = OTPVerifySerializer(
            data={"email": "user@example.com", "otp": "123456"}
        )
        with self.assertRaises(RedisUnavailableError):
            serializer.is_valid(raise_exception=True)


class OTPRequestViewTests(SimpleTestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/api/v1/auth/otp/request"

    @patch("apps.accounts.views.write_audit_log.delay")
    @patch("apps.accounts.views.send_otp_email.delay")
    @patch("apps.accounts.views.set_otp")
    @patch("apps.accounts.serializers.check_ip_limit")
    @patch("apps.accounts.serializers.check_email_limit")
    def test_success_returns_202_and_enqueues_tasks(
        self,
        mock_check_email,
        mock_check_ip,
        mock_set_otp,
        mock_send_otp_delay,
        mock_audit_delay,
    ):
        mock_check_email.return_value = (True, 0)
        mock_check_ip.return_value = (True, 0)
        mock_set_otp.return_value = True

        response = self.client.post(
            self.url,
            {"email": "user@example.com"},
            format="json",
            HTTP_X_FORWARDED_FOR="1.2.3.4",
            HTTP_USER_AGENT="pytest-agent",
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["expires_in"], 300)
        mock_send_otp_delay.assert_called_once()
        mock_audit_delay.assert_called_once()

    @patch("apps.accounts.serializers.check_email_limit")
    def test_rate_limited_returns_429(self, mock_check_email):
        mock_check_email.return_value = (False, 99)

        response = self.client.post(
            self.url, {"email": "user@example.com"}, format="json"
        )

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.data["limit_type"], "email")
        self.assertEqual(response.data["retry_after"], 99)
        self.assertIsInstance(response.data["retry_after"], int)

    @patch("apps.accounts.serializers.check_email_limit")
    def test_redis_unavailable_returns_503(self, mock_check_email):
        mock_check_email.side_effect = RedisUnavailableError("Redis is unavailable")

        response = self.client.post(
            self.url, {"email": "user@example.com"}, format="json"
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["detail"], "Service temporarily unavailable")


class OTPVerifyViewTests(SimpleTestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/api/v1/auth/otp/verify"

    @patch("apps.accounts.views.write_audit_log.delay")
    @patch("apps.accounts.views.generate_tokens_for_user")
    @patch("apps.accounts.views.get_or_create_active_user")
    @patch("apps.accounts.views.reset_failed_attempts")
    @patch("apps.accounts.views.consume_otp")
    @patch("apps.accounts.serializers.get_otp")
    @patch("apps.accounts.serializers.is_locked")
    def test_verify_success_returns_200(
        self,
        mock_is_locked,
        mock_get_otp,
        mock_consume,
        mock_reset,
        mock_get_user,
        mock_tokens,
        mock_audit,
    ):
        mock_is_locked.return_value = (False, 0)
        mock_get_otp.return_value = "123456"
        mock_consume.return_value = "123456"
        mock_get_user.return_value = object()
        mock_tokens.return_value = {"access": "a", "refresh": "r"}

        response = self.client.post(
            self.url,
            {"email": "user@example.com", "otp": "123456"},
            format="json",
            HTTP_X_FORWARDED_FOR="1.2.3.4",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["access"], "a")
        mock_reset.assert_called_once()
        mock_audit.assert_called_once()

    @patch("apps.accounts.views.write_audit_log.delay")
    @patch("apps.accounts.serializers.get_failed_attempts_ttl")
    @patch("apps.accounts.serializers.increment_failed_attempt")
    @patch("apps.accounts.serializers.get_otp")
    @patch("apps.accounts.serializers.is_locked")
    def test_verify_wrong_otp_returns_400(
        self,
        mock_is_locked,
        mock_get_otp,
        mock_increment,
        mock_ttl,
        mock_audit,
    ):
        mock_is_locked.return_value = (False, 0)
        mock_get_otp.return_value = "654321"
        mock_increment.return_value = 1
        mock_ttl.return_value = 840

        response = self.client.post(
            self.url,
            {"email": "user@example.com", "otp": "123456"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "Invalid OTP")
        mock_audit.assert_called_once()

    @patch("apps.accounts.views.write_audit_log.delay")
    @patch("apps.accounts.serializers.is_locked")
    def test_verify_locked_returns_423(self, mock_is_locked, mock_audit):
        mock_is_locked.return_value = (True, 900)

        response = self.client.post(
            self.url,
            {"email": "user@example.com", "otp": "123456"},
            format="json",
        )

        self.assertEqual(response.status_code, 423)
        self.assertEqual(response.data["detail"], "Account temporarily locked")
        self.assertIn("retry_after", response.data)
        self.assertIsInstance(response.data["retry_after"], int)
        mock_audit.assert_called_once()

    @patch("apps.accounts.serializers.is_locked")
    def test_verify_redis_unavailable_returns_503(self, mock_is_locked):
        mock_is_locked.side_effect = RedisUnavailableError("Redis is unavailable")

        response = self.client.post(
            self.url,
            {"email": "user@example.com", "otp": "123456"},
            format="json",
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["detail"], "Service temporarily unavailable")

    @patch("apps.accounts.views.write_audit_log.delay")
    @patch("apps.accounts.views.generate_tokens_for_user")
    @patch("apps.accounts.views.get_or_create_active_user")
    @patch("apps.accounts.views.reset_failed_attempts")
    @patch("apps.accounts.views.consume_otp")
    @patch("apps.accounts.serializers.get_otp")
    @patch("apps.accounts.serializers.is_locked")
    def test_verify_success_with_audit_enqueue_failure_still_returns_200(
        self,
        mock_is_locked,
        mock_get_otp,
        mock_consume,
        mock_reset,
        mock_get_user,
        mock_tokens,
        mock_audit,
    ):
        mock_is_locked.return_value = (False, 0)
        mock_get_otp.return_value = "123456"
        mock_consume.return_value = "123456"
        mock_get_user.return_value = object()
        mock_tokens.return_value = {"access": "a", "refresh": "r"}
        mock_audit.side_effect = RuntimeError("broker unavailable")

        response = self.client.post(
            self.url,
            {"email": "user@example.com", "otp": "123456"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["access"], "a")

    @patch("apps.accounts.views.write_audit_log.delay")
    @patch("apps.accounts.views.get_failed_attempts_ttl")
    @patch("apps.accounts.views.increment_failed_attempt")
    @patch("apps.accounts.views.consume_otp")
    @patch("apps.accounts.serializers.get_otp")
    @patch("apps.accounts.serializers.is_locked")
    def test_verify_race_mismatch_returns_400(
        self,
        mock_is_locked,
        mock_get_otp,
        mock_consume,
        mock_increment,
        mock_ttl,
        mock_audit,
    ):
        mock_is_locked.return_value = (False, 0)
        mock_get_otp.return_value = "123456"
        mock_consume.return_value = "000000"
        mock_increment.return_value = 1
        mock_ttl.return_value = 850

        response = self.client.post(
            self.url,
            {"email": "user@example.com", "otp": "123456"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "Invalid OTP")
        mock_audit.assert_called_once()

    @patch("apps.accounts.views.write_audit_log.delay")
    @patch("apps.accounts.views.generate_tokens_for_user")
    @patch("apps.accounts.views.get_or_create_active_user")
    @patch("apps.accounts.views.reset_failed_attempts")
    @patch("apps.accounts.views.get_failed_attempts_ttl")
    @patch("apps.accounts.views.increment_failed_attempt")
    @patch("apps.accounts.views.consume_otp")
    @patch("apps.accounts.serializers.get_otp")
    @patch("apps.accounts.serializers.is_locked")
    def test_one_time_otp_sequential_requests_first_success_second_fails(
        self,
        mock_is_locked,
        mock_get_otp,
        mock_consume,
        mock_increment,
        mock_ttl,
        mock_reset,
        mock_get_user,
        mock_tokens,
        mock_audit,
    ):
        mock_is_locked.return_value = (False, 0)
        mock_get_otp.side_effect = ["123456", None]
        mock_consume.return_value = "123456"
        mock_increment.return_value = 1
        mock_ttl.return_value = 850
        mock_get_user.return_value = object()
        mock_tokens.return_value = {"access": "a", "refresh": "r"}

        response1 = self.client.post(
            self.url,
            {"email": "user@example.com", "otp": "123456"},
            format="json",
        )
        response2 = self.client.post(
            self.url,
            {"email": "user@example.com", "otp": "123456"},
            format="json",
        )

        self.assertEqual(response1.status_code, 200)
        self.assertEqual(response2.status_code, 400)
        self.assertEqual(response2.data["detail"], "Invalid OTP")


class UserTokenServiceTests(TestCase):
    def test_get_or_create_active_user_creates_user(self):
        from apps.accounts.services.user_service import get_or_create_active_user

        user = get_or_create_active_user("new@example.com")
        self.assertEqual(user.email, "new@example.com")
        self.assertTrue(user.is_active)
        self.assertIsNotNone(user.last_login)

    def test_get_or_create_active_user_reactivates_user(self):
        from apps.accounts.services.user_service import get_or_create_active_user

        user = User.objects.create(email="inactive@example.com", is_active=False)
        updated_user = get_or_create_active_user(user.email)
        self.assertTrue(updated_user.is_active)
        self.assertIsNotNone(updated_user.last_login)

    def test_generate_tokens_for_user(self):
        from apps.accounts.services.token_service import generate_tokens_for_user

        user = User.objects.create(email="token@example.com", is_active=True)
        tokens = generate_tokens_for_user(user)
        self.assertIn("access", tokens)
        self.assertIn("refresh", tokens)
        self.assertTrue(tokens["access"])
        self.assertTrue(tokens["refresh"])


class OTPTaskTests(TestCase):
    def test_send_otp_email_logs(self):
        from apps.accounts.tasks import send_otp_email

        with patch("builtins.print") as mock_print:
            send_otp_email.run("user@example.com", "123456")
        mock_print.assert_called_once()

    def test_send_otp_email_retry_config(self):
        from apps.accounts.tasks import send_otp_email

        self.assertEqual(send_otp_email.max_retries, 3)
        self.assertIn(Exception, send_otp_email.autoretry_for)

    def test_write_audit_log_creates_record(self):
        from apps.audit.models import AuditEvent, AuditLog
        from apps.audit.tasks import write_audit_log

        write_audit_log.run(
            event=AuditEvent.OTP_REQUESTED,
            email="user@example.com",
            ip_address="127.0.0.1",
            user_agent="pytest-agent",
            metadata={"source": "test"},
        )
        self.assertEqual(AuditLog.objects.count(), 1)
