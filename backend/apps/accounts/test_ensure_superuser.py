"""ensure_superuser: first admin on hosts without a shell, never touching existing accounts."""

from io import StringIO
from unittest import mock

from django.contrib.auth import authenticate
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.accounts.models import User
from apps.operations.models import AuditLog

GOOD = {"DJANGO_SUPERUSER_EMAIL": "Admin@Tutor.test", "DJANGO_SUPERUSER_PASSWORD": "Strong-admin-pass-2026"}


def run(env):
    out = StringIO()
    with mock.patch.dict("os.environ", env, clear=False):
        call_command("ensure_superuser", stdout=out)
    return out.getvalue()


class EnsureSuperuserTests(TestCase):
    def setUp(self):
        patcher = mock.patch.dict(
            "os.environ", {"DJANGO_SUPERUSER_EMAIL": "", "DJANGO_SUPERUSER_PASSWORD": "", "DJANGO_SUPERUSER_NAME": ""}
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_skips_when_not_configured(self):
        self.assertIn("skipped", run({}))
        self.assertFalse(User.objects.exists())

    def test_creates_superuser_once(self):
        self.assertIn("created", run(GOOD))
        user = User.objects.get(email="admin@tutor.test")
        self.assertTrue(user.is_superuser and user.is_staff)
        self.assertIsNotNone(
            authenticate(None, username="admin@tutor.test", password=GOOD["DJANGO_SUPERUSER_PASSWORD"])
        )
        self.assertTrue(AuditLog.objects.filter(action="user.superuser_created").exists())
        self.assertIn("is a superuser", run(GOOD))  # second deploy: no-op
        self.assertEqual(User.objects.count(), 1)

    def test_never_resets_an_existing_password(self):
        run(GOOD)
        run(dict(GOOD, DJANGO_SUPERUSER_PASSWORD="Another-strong-pass-2026"))
        self.assertIsNotNone(
            authenticate(None, username="admin@tutor.test", password=GOOD["DJANGO_SUPERUSER_PASSWORD"])
        )

    def test_never_promotes_an_existing_ordinary_account(self):
        User.objects.create_user(email="admin@tutor.test", password="x-long-pass-1", full_name="Someone")
        self.assertIn("NOT a superuser", run(GOOD))
        self.assertFalse(User.objects.get(email="admin@tutor.test").is_superuser)

    def test_weak_password_is_refused(self):
        with self.assertRaises(CommandError):
            run(dict(GOOD, DJANGO_SUPERUSER_PASSWORD="password"))
        self.assertFalse(User.objects.exists())
