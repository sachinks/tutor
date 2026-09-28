from django.contrib.auth import authenticate, get_user_model
from django.db import IntegrityError
from django.test import TestCase

User = get_user_model()


class UserModelTests(TestCase):
    def test_create_with_email(self):
        user = User.objects.create_user(email="Asha@Example.com", password="s3cret-pass", full_name="Asha")
        self.assertEqual(user.email, "asha@example.com")
        self.assertIsNone(user.mobile)

    def test_create_with_mobile_only(self):
        user = User.objects.create_user(mobile="+919876543210", password="s3cret-pass", full_name="Ravi")
        self.assertIsNone(user.email)

    def test_needs_email_or_mobile(self):
        with self.assertRaises(ValueError):
            User.objects.create_user(password="x", full_name="Nobody")

    def test_database_enforces_email_or_mobile(self):
        with self.assertRaises(IntegrityError):
            User.objects.bulk_create([User(full_name="Nobody")])

    def test_superuser(self):
        admin = User.objects.create_superuser(email="admin@tutor.test", password="s3cret-pass", full_name="Admin")
        self.assertTrue(admin.is_staff and admin.is_superuser)
        self.assertEqual(admin.account_type, "staff")


class LoginTests(TestCase):
    def setUp(self):
        User.objects.create_user(
            email="parent@example.com", mobile="+919812345678", password="s3cret-pass", full_name="Parent"
        )

    def test_login_with_email(self):
        self.assertIsNotNone(authenticate(username="PARENT@example.com", password="s3cret-pass"))

    def test_login_with_mobile(self):
        self.assertIsNotNone(authenticate(username="+919812345678", password="s3cret-pass"))

    def test_wrong_password(self):
        self.assertIsNone(authenticate(username="parent@example.com", password="nope"))


class HealthTests(TestCase):
    def test_health(self):
        response = self.client.get("/api/v1/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, "db": True})


# ---------------------------------------------------------------------------
# Profiles, guardians, consent, approvals, roles
# ---------------------------------------------------------------------------
from datetime import timedelta  # noqa: E402

from django.core.management import call_command  # noqa: E402
from django.utils import timezone  # noqa: E402

from apps.accounts.models import (  # noqa: E402
    ApprovalRequest,
    ConsentRecord,
    ConsentText,
    GuardianLink,
    RoleGrant,
    StudentProfile,
    has_role,
)
from apps.accounts.tokens import hash_secret, make_link_token, make_otp  # noqa: E402
from apps.catalogue.models import Board, ClassLevel, Subject  # noqa: E402


class ReferenceDataMixin:
    @classmethod
    def setUpTestData(cls):
        call_command("seed_reference", verbosity=0)
        cls.class8 = ClassLevel.objects.get(number=8)
        cls.cbse = Board.objects.get(code="CBSE")
        cls.maths = Subject.objects.get(slug="mathematics")


class SeedTests(ReferenceDataMixin, TestCase):
    def test_seed_is_idempotent(self):
        call_command("seed_reference", verbosity=0)
        self.assertEqual(ClassLevel.objects.count(), 7)
        self.assertEqual(Board.objects.count(), 3)


class GuardianConsentTests(ReferenceDataMixin, TestCase):
    def setUp(self):
        self.student = User.objects.create_user(mobile="+919800000001", password="pw-123456", full_name="Riya")
        StudentProfile.objects.create(user=self.student, class_level=self.class8, board=self.cbse, city="Kolkata")
        self.mum = User.objects.create_user(mobile="+919800000002", password="pw-123456", full_name="Mum")
        self.dad = User.objects.create_user(mobile="+919800000003", password="pw-123456", full_name="Dad")

    def test_new_student_awaits_consent(self):
        self.assertEqual(self.student.student_profile.status, StudentProfile.Status.AWAITING_CONSENT)

    def test_only_one_active_primary_guardian(self):
        GuardianLink.objects.create(parent=self.mum, student=self.student)
        with self.assertRaises(IntegrityError):
            GuardianLink.objects.create(parent=self.dad, student=self.student)

    def test_ended_link_frees_primary_slot(self):
        link = GuardianLink.objects.create(parent=self.mum, student=self.student)
        link.ended_at = timezone.now()
        link.save()
        GuardianLink.objects.create(parent=self.dad, student=self.student)  # no error

    def test_consent_record_active_until_withdrawn(self):
        text = ConsentText.objects.create(version="test-v1", body="…", effective_from=timezone.localdate())
        link = GuardianLink.objects.create(parent=self.mum, student=self.student)
        consent = ConsentRecord.objects.create(guardian_link=link, consent_text=text, given_ip="127.0.0.1")
        self.assertTrue(consent.is_active)
        consent.withdrawn_at = timezone.now()
        self.assertFalse(consent.is_active)
        self.assertEqual(ConsentText.current(), text)


class TokenAndApprovalTests(ReferenceDataMixin, TestCase):
    def test_link_token_stored_only_as_hash(self):
        raw, hashed = make_link_token()
        self.assertNotEqual(raw, hashed)
        self.assertEqual(hash_secret(raw), hashed)

    def test_otp_is_six_digits(self):
        raw, hashed = make_otp()
        self.assertRegex(raw, r"^\d{6}$")
        self.assertEqual(len(hashed), 64)

    def test_approval_request_expiry(self):
        student = User.objects.create_user(mobile="+919800000009", password="pw-123456", full_name="Kid")
        _, hashed = make_link_token()
        req = ApprovalRequest.objects.create(
            student=student, parent_contact="+919800000010", channel="sms", token_hash=hashed,
            expires_at=timezone.now() + timedelta(days=ApprovalRequest.VALID_DAYS),
        )
        self.assertTrue(req.is_usable)
        req.expires_at = timezone.now() - timedelta(seconds=1)
        self.assertFalse(req.is_usable)


class RoleTests(ReferenceDataMixin, TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(email="t@example.com", password="pw-123456", full_name="Teacher")

    def test_scoped_role(self):
        RoleGrant.objects.create(user=self.teacher, role="reviewer", subject=self.maths, class_level=self.class8)
        self.assertTrue(has_role(self.teacher, "reviewer", subject=self.maths, class_level=self.class8))
        class11 = ClassLevel.objects.get(number=11)
        self.assertFalse(has_role(self.teacher, "reviewer", subject=self.maths, class_level=class11))

    def test_revoked_role(self):
        grant = RoleGrant.objects.create(user=self.teacher, role="author", subject=self.maths)
        grant.revoked_at = timezone.now()
        grant.save()
        self.assertFalse(has_role(self.teacher, "author", subject=self.maths))

    def test_no_duplicate_active_grant(self):
        RoleGrant.objects.create(user=self.teacher, role="operations")
        with self.assertRaises(IntegrityError):
            RoleGrant.objects.create(user=self.teacher, role="operations")
