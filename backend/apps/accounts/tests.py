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
