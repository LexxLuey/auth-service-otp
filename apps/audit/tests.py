from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User
from apps.audit.serializers import AuditLogSerializer

from apps.audit.models import AuditEvent, AuditLog


class AuditLogModelTests(TestCase):
    def test_create_audit_log_with_required_fields(self):
        log = AuditLog.objects.create(
            event=AuditEvent.OTP_REQUESTED,
            email="user@example.com",
        )
        self.assertEqual(log.event, AuditEvent.OTP_REQUESTED)
        self.assertEqual(log.metadata, {})

    def test_event_choice_validation(self):
        log = AuditLog(event="INVALID_EVENT", email="user@example.com")
        with self.assertRaises(ValidationError):
            log.full_clean()

    def test_metadata_json_field(self):
        payload = {"attempt": 2, "reason": "wrong_otp"}
        log = AuditLog.objects.create(
            event=AuditEvent.OTP_FAILED,
            email="user@example.com",
            metadata=payload,
        )
        self.assertEqual(log.metadata, payload)

    def test_default_ordering_by_created_at_desc(self):
        older = AuditLog.objects.create(
            event=AuditEvent.OTP_REQUESTED,
            email="older@example.com",
        )
        newer = AuditLog.objects.create(
            event=AuditEvent.OTP_VERIFIED,
            email="newer@example.com",
        )
        older.created_at = timezone.now() - timedelta(hours=1)
        older.save(update_fields=["created_at"])

        logs = list(AuditLog.objects.all())
        self.assertEqual(logs[0].id, newer.id)
        self.assertEqual(logs[1].id, older.id)

    def test_audit_log_str_representation(self):
        log = AuditLog.objects.create(
            event=AuditEvent.OTP_REQUESTED,
            email="user@example.com",
        )
        self.assertEqual(str(log), "OTP_REQUESTED - user@example.com")

    def test_audit_log_serializer_is_read_only(self):
        log = AuditLog.objects.create(
            event=AuditEvent.OTP_REQUESTED,
            email="user@example.com",
        )
        serializer = AuditLogSerializer(
            instance=log,
            data={
                "id": 999,
                "event": "OTP_FAILED",
                "email": "changed@example.com",
                "created_at": "2026-03-02T10:30:00Z",
            },
            partial=True,
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data, {})


class AuditLogAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/api/v1/audit/logs"

        self.user = User.objects.create(email="apiuser@example.com", is_active=True)
        token = RefreshToken.for_user(self.user).access_token
        self.auth_header = f"Bearer {token}"

        self.log1 = AuditLog.objects.create(
            event=AuditEvent.OTP_REQUESTED,
            email="user1@example.com",
            metadata={"source": "otp_request"},
        )
        self.log2 = AuditLog.objects.create(
            event=AuditEvent.OTP_VERIFIED,
            email="user2@example.com",
            metadata={"source": "otp_verify"},
        )
        self.log3 = AuditLog.objects.create(
            event=AuditEvent.OTP_FAILED,
            email="user1@example.com",
            metadata={"source": "otp_verify"},
        )

        self.log1.created_at = timezone.now() - timedelta(hours=2)
        self.log1.save(update_fields=["created_at"])
        self.log2.created_at = timezone.now() - timedelta(hours=1)
        self.log2.save(update_fields=["created_at"])
        self.log3.created_at = timezone.now()
        self.log3.save(update_fields=["created_at"])

    def test_requires_authentication(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 401)

    def test_returns_paginated_response_when_authenticated(self):
        response = self.client.get(self.url, HTTP_AUTHORIZATION=self.auth_header)
        self.assertEqual(response.status_code, 200)
        self.assertIn("count", response.data)
        self.assertIn("next", response.data)
        self.assertIn("previous", response.data)
        self.assertIn("results", response.data)

    def test_default_ordering_newest_first(self):
        response = self.client.get(self.url, HTTP_AUTHORIZATION=self.auth_header)
        self.assertEqual(response.status_code, 200)
        result_ids = [item["id"] for item in response.data["results"]]
        self.assertEqual(result_ids[:3], [self.log3.id, self.log2.id, self.log1.id])

    def test_filter_by_email_exact(self):
        response = self.client.get(
            f"{self.url}?email=user1@example.com", HTTP_AUTHORIZATION=self.auth_header
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        self.assertTrue(
            all(
                item["email"] == "user1@example.com"
                for item in response.data["results"]
            )
        )

    def test_filter_by_event_exact(self):
        response = self.client.get(
            f"{self.url}?event=OTP_VERIFIED", HTTP_AUTHORIZATION=self.auth_header
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["event"], "OTP_VERIFIED")

    def test_filter_by_from_date(self):
        from_date = (timezone.now() - timedelta(hours=1, minutes=30)).isoformat()
        response = self.client.get(
            self.url,
            {"from_date": from_date},
            HTTP_AUTHORIZATION=self.auth_header,
        )
        self.assertEqual(response.status_code, 200)
        result_ids = [item["id"] for item in response.data["results"]]
        self.assertIn(self.log2.id, result_ids)
        self.assertIn(self.log3.id, result_ids)
        self.assertNotIn(self.log1.id, result_ids)

    def test_filter_by_to_date(self):
        to_date = (timezone.now() - timedelta(hours=1, minutes=30)).isoformat()
        response = self.client.get(
            self.url,
            {"to_date": to_date},
            HTTP_AUTHORIZATION=self.auth_header,
        )
        self.assertEqual(response.status_code, 200)
        result_ids = [item["id"] for item in response.data["results"]]
        self.assertIn(self.log1.id, result_ids)
        self.assertNotIn(self.log2.id, result_ids)
        self.assertNotIn(self.log3.id, result_ids)

    def test_invalid_datetime_returns_400(self):
        response = self.client.get(
            f"{self.url}?from_date=not-a-datetime",
            HTTP_AUTHORIZATION=self.auth_header,
        )
        self.assertEqual(response.status_code, 400)

    def test_ordering_created_at_oldest_first(self):
        response = self.client.get(
            f"{self.url}?ordering=created_at", HTTP_AUTHORIZATION=self.auth_header
        )
        self.assertEqual(response.status_code, 200)
        result_ids = [item["id"] for item in response.data["results"]]
        self.assertEqual(result_ids[:3], [self.log1.id, self.log2.id, self.log3.id])
