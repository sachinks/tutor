"""Shared plumbing: the dev outbox (tester tool) and the read-only audit log admin."""

from django.contrib.admin.sites import site
from django.test import RequestFactory, SimpleTestCase, TestCase

from apps.accounts.models import User
from apps.core import messaging
from apps.core.dev_api import outbox
from apps.operations.models import AuditLog


class DevOutboxTests(SimpleTestCase):
    """The view itself; that it is unreachable outside local development is tested in accounts.tests."""

    def setUp(self):
        messaging.OUTBOX.clear()
        self.addCleanup(messaging.OUTBOX.clear)
        for n in range(3):
            messaging.send("sms", "+919000000001", f"message {n}")
        messaging.send("email", "a@test.tutor", "other")
        self.request = RequestFactory().get("/")

    def test_newest_first_and_filtered_by_recipient(self):
        texts = [m["text"] for m in outbox(self.request, to="+919000000001")]
        self.assertEqual(texts, ["message 2", "message 1", "message 0"])

    def test_limit_is_clamped(self):
        self.assertEqual(len(outbox(self.request, limit=1)), 1)
        self.assertEqual(len(outbox(self.request, limit=0)), 1)  # at least one
        self.assertEqual(len(outbox(self.request, limit=999)), 4)  # at most 50; only 4 exist


class AuditLogAdminTests(TestCase):
    def test_audit_log_is_read_only_even_for_superusers(self):
        superuser = User.objects.create_superuser(email="su@example.com", password="x-long-pass-1", full_name="Su")
        request = RequestFactory().get("/admin/")
        request.user = superuser
        audit_admin = site._registry[AuditLog]
        self.assertFalse(audit_admin.has_add_permission(request))
        self.assertFalse(audit_admin.has_change_permission(request))
        self.assertFalse(audit_admin.has_delete_permission(request))
