"""End-to-end tests for the accounts & consent API (journeys S4–S5, P1–P2, P8)."""

import json
import re

from django.core.cache import cache
from django.core.management import call_command
from django.test import Client, TestCase

from apps.accounts.models import ApprovalRequest, StudentProfile, User
from apps.core import messaging
from apps.operations.models import AuditLog

STUDENT = {
    "full_name": "Riya Sen",
    "mobile": "9800000001",
    "password": "Learn-2026-ok",
    "class_number": 8,
    "board_code": "cbse",
    "city": "Kolkata",
    "parent_contact": "9800000002",
}
PARENT = {"full_name": "Mita Sen", "mobile": "9800000002", "password": "Parent-2026-ok"}


def post(client, path, data=None, method="post"):
    fn = getattr(client, method)
    return fn(f"/api/v1{path}", data=json.dumps(data or {}), content_type="application/json")


def last_message_to(to):
    for msg in reversed(messaging.OUTBOX):
        if msg["to"] == to:
            return msg["text"]
    raise AssertionError(f"no message to {to}")


def link_token(text):
    return re.search(r"/approve/([A-Za-z0-9_-]+)", text).group(1)


def otp(text):
    return re.search(r"code is (\d{6})", text).group(1)


class ApiTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_reference", verbosity=0)
        call_command("seed_consent", verbosity=0)

    def setUp(self):
        cache.clear()  # rate-limit and lockout counters must not leak between tests
        messaging.OUTBOX.clear()
        self.student_client = Client()
        self.parent_client = Client()

    def signup_student(self):
        res = post(self.student_client, "/auth/signup/student", STUDENT)
        self.assertEqual(res.status_code, 201, res.content)
        return res.json()

    def signup_verified_parent(self):
        res = post(self.parent_client, "/auth/signup/parent", PARENT)
        self.assertEqual(res.status_code, 201, res.content)
        code = otp(last_message_to("+919800000002"))
        res = post(
            self.parent_client,
            "/auth/otp/verify",
            {"destination": "9800000002", "purpose": "verify_contact", "code": code},
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertTrue(res.json()["mobile_verified"])


class SignupAndApprovalFlow(ApiTestCase):
    def test_student_signup_waits_for_parent(self):
        me = self.signup_student()
        self.assertEqual(me["student"]["status"], "awaiting_consent")
        self.assertEqual(me["mobile"], "+919800000001")
        self.assertIn("/approve/", last_message_to("+919800000002"))  # link to parent
        self.assertIn("code is", last_message_to("+919800000001"))  # OTP to student

    def test_full_approval(self):
        self.signup_student()
        token = link_token(last_message_to("+919800000002"))
        self.signup_verified_parent()

        details = self.parent_client.get(f"/api/v1/consent/link/{token}").json()
        self.assertEqual(details["child_first_name"], "Riya")
        self.assertEqual(details["class_label"], "Class 8")

        res = post(self.parent_client, f"/consent/link/{token}/approve", {"relationship": "mother", "accept": True})
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(self.student_client.get("/api/v1/me").json()["student"]["status"], "active")
        self.assertEqual(len(self.parent_client.get("/api/v1/me").json()["children"]), 1)
        self.assertTrue(AuditLog.objects.filter(action="consent.given").exists())

        # the same link can't be used twice
        res = post(self.parent_client, f"/consent/link/{token}/approve", {"accept": True})
        self.assertEqual(res.status_code, 410)

    def test_parent_must_verify_contact_first(self):
        self.signup_student()
        token = link_token(last_message_to("+919800000002"))
        post(self.parent_client, "/auth/signup/parent", PARENT)  # not verified
        res = post(self.parent_client, f"/consent/link/{token}/approve", {"accept": True})
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["error"]["code"], "contact_not_verified")

    def test_not_my_child(self):
        self.signup_student()
        token = link_token(last_message_to("+919800000002"))
        self.assertEqual(post(Client(), f"/consent/link/{token}/report").status_code, 200)
        self.assertEqual(Client().get(f"/api/v1/consent/link/{token}").status_code, 410)
        self.assertEqual(ApprovalRequest.objects.get().status, "reported")

    def test_resend_limit(self):
        self.signup_student()
        self.assertEqual(post(self.student_client, "/consent/requests/resend").status_code, 200)
        self.assertEqual(post(self.student_client, "/consent/requests/resend").status_code, 200)
        res = post(self.student_client, "/consent/requests/resend")
        self.assertEqual(res.status_code, 429)
        self.assertEqual(res.json()["error"]["code"], "limit_reached")

    def test_change_parent_contact(self):
        self.signup_student()
        res = post(
            self.student_client,
            "/consent/requests/parent-contact",
            {"parent_contact": "father@example.com"},
            method="patch",
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertIn("/approve/", last_message_to("father@example.com"))
        self.assertEqual(ApprovalRequest.objects.filter(status="sent").count(), 1)


class LoginAndErrors(ApiTestCase):
    def test_login_with_plain_10_digit_mobile(self):
        self.signup_student()
        res = post(Client(), "/auth/login", {"identifier": "98000 00001", "password": STUDENT["password"]})
        self.assertEqual(res.status_code, 200, res.content)

    def test_wrong_password(self):
        self.signup_student()
        res = post(Client(), "/auth/login", {"identifier": "9800000001", "password": "nope"})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "invalid_credentials")

    def test_duplicate_signup(self):
        self.signup_student()
        res = post(Client(), "/auth/signup/student", STUDENT)
        self.assertEqual(res.status_code, 409)

    def test_validation_error_format(self):
        res = post(Client(), "/auth/signup/student", {"full_name": "X"})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "validation_error")

    def test_me_requires_login(self):
        res = Client().get("/api/v1/me")
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["error"]["code"], "not_authenticated")

    def test_otp_not_sent_to_unknown_contact(self):
        res = post(Client(), "/auth/otp/send", {"destination": "9811111111", "purpose": "login"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(messaging.OUTBOX, [])

    def test_password_reset(self):
        self.signup_student()
        post(Client(), "/auth/otp/send", {"destination": "9800000001", "purpose": "reset_password"})
        code = otp(last_message_to("+919800000001"))
        res = post(
            Client(),
            "/auth/password/reset",
            {"destination": "9800000001", "code": code, "new_password": "Brand-new-2026"},
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(
            post(Client(), "/auth/login", {"identifier": "9800000001", "password": "Brand-new-2026"}).status_code, 200
        )


class ParentManagesChildren(ApiTestCase):
    def test_add_child_withdraw_and_restore(self):
        self.signup_verified_parent()
        res = post(
            self.parent_client,
            "/parent/children",
            {
                "full_name": "Arjun Sen",
                "email": "arjun@example.com",
                "password": "Child-2026-ok",
                "class_number": 10,
                "board_code": "ICSE",
                "city": "Kolkata",
                "relationship": "mother",
            },
        )
        self.assertEqual(res.status_code, 201, res.content)
        child_id = res.json()["id"]
        self.assertEqual(res.json()["status"], "active")

        self.assertEqual(post(self.parent_client, f"/parent/children/{child_id}/consent/withdraw").status_code, 200)
        self.assertEqual(StudentProfile.objects.get(user_id=child_id).status, "paused")
        self.assertEqual(post(self.parent_client, f"/parent/children/{child_id}/consent/restore").status_code, 200)
        self.assertEqual(StudentProfile.objects.get(user_id=child_id).status, "active")

    def test_other_parent_cannot_touch_child(self):
        self.signup_verified_parent()
        res = post(
            self.parent_client,
            "/parent/children",
            {
                "full_name": "Arjun Sen",
                "email": "arjun@example.com",
                "password": "Child-2026-ok",
                "class_number": 10,
                "board_code": "ICSE",
                "city": "Kolkata",
            },
        )
        child_id = res.json()["id"]
        stranger = Client()
        User.objects.create_user(email="x@example.com", password="Stranger-2026", full_name="X", account_type="parent")
        post(stranger, "/auth/login", {"identifier": "x@example.com", "password": "Stranger-2026"})
        self.assertEqual(post(stranger, f"/parent/children/{child_id}/consent/withdraw").status_code, 404)


class SecureByDefaultTests(ApiTestCase):
    def test_docs_page_sends_csrf_token(self):
        """TC-SET-3: the /docs page must send X-CSRFToken so logged-in POSTs work from Swagger."""
        html = self.client.get("/api/v1/docs").content.decode()
        self.assertTrue('data-api-csrf="true"' in html or "X-CSRFToken" in html)

    def test_public_endpoints_stay_public(self):
        anon = Client()
        self.assertEqual(anon.get("/api/v1/health").status_code, 200)
        self.assertEqual(anon.get("/api/v1/catalogue/facets").status_code, 200)
        self.assertEqual(anon.get("/api/v1/courses/ai-foundations").status_code, 404)  # public, just no demo data here
        self.assertEqual(anon.get("/api/v1/auth/csrf").status_code, 200)

    def test_protected_endpoints_need_login(self):
        anon = Client()
        for path in ("/api/v1/me", "/api/v1/student/today", "/api/v1/student/record"):
            self.assertEqual(anon.get(path).status_code, 401, path)
