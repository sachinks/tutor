"""Authorization, end to end, for every endpoint (NFR-SEC-1, FR-LRN-1, FR-LRN-2).

1. Secure by default: every operation in the API is called anonymously. Exactly the operations listed in PUBLIC may
   answer without a login; every other one must answer 401. A new endpoint that forgets `auth` either shows up here as
   unexpectedly public, or is protected, so this test can't be satisfied by accident.
2. Who-may-do-what matrix for learning endpoints, using the demo world's people in every state.
3. CSRF is enforced on logged-in state changes.
"""

import re
import uuid
from io import StringIO

from django.core.management import call_command
from django.test import Client, TestCase, override_settings

from apps.accounts.models import User
from apps.catalogue.models import Lesson
from apps.demo.people import BY_KEY

PUBLIC = {
    ("GET", "/api/v1/health"),
    ("GET", "/api/v1/auth/csrf"),
    ("POST", "/api/v1/auth/otp/send"),
    ("POST", "/api/v1/auth/otp/verify"),
    ("POST", "/api/v1/auth/password/reset"),
    ("POST", "/api/v1/auth/signup/student"),
    ("POST", "/api/v1/auth/signup/parent"),
    ("POST", "/api/v1/auth/login"),
    ("GET", "/api/v1/consent/link/{token}"),
    ("POST", "/api/v1/consent/link/{token}/report"),
    ("GET", "/api/v1/catalogue/facets"),
    ("GET", "/api/v1/catalogue/items"),
    ("GET", "/api/v1/courses/{slug}"),
    ("GET", "/api/v1/programmes/{slug}"),
    ("GET", "/api/v1/lessons/{lesson_id}/preview"),
}
PLACEHOLDER = re.compile(r"\{(\w+)\}")
PASSWORD = "Matrix-Pass-2026-x"


def api_operations():
    from config.api import api

    schema = api.get_openapi_schema()
    for path, methods in schema["paths"].items():
        for method in methods:
            if method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                yield method.upper(), path


def concrete(path):
    """Fill path parameters with harmless values: a random UUID works for ids, slugs and tokens alike."""
    return PLACEHOLDER.sub(lambda _: str(uuid.uuid4()), path)


class SecureByDefaultMatrixTests(TestCase):
    def test_every_operation_is_either_listed_public_or_needs_login(self):
        anonymous = Client()
        seen, unexpectedly_public, missing_login = set(), [], []
        for method, path in api_operations():
            seen.add((method, path))
            response = anonymous.generic(method, concrete(path), data="{}", content_type="application/json")
            is_public = (method, path) in PUBLIC
            if response.status_code == 401 and is_public:
                missing_login.append(f"{method} {path} is listed public but answered 401")
            if response.status_code != 401 and not is_public:
                unexpectedly_public.append(f"{method} {path} answered {response.status_code} without a login")
        self.assertEqual(unexpectedly_public, [], "Add auth, or list the endpoint in PUBLIC after a security review.")
        self.assertEqual(missing_login, [])
        self.assertEqual(PUBLIC - seen, set(), "PUBLIC lists endpoints that no longer exist")
        self.assertGreater(len(seen), len(PUBLIC))  # the API has protected endpoints at all


@override_settings(TUTOR_DEMO_DATA=True, TUTOR_DEMO_PASSWORD=PASSWORD)
class LearningAccessMatrixTests(TestCase):
    """Rows: who is asking. Columns: free lesson, paid lesson, Today. Expected: status or error code."""

    FREE = "what-are-rational-numbers"  # Maths 8, module 1 (free)
    PAID = "solving-linear-equations"  # Maths 8, module 2 (paid)
    MATRIX = {
        # key:              (free lesson,        paid lesson,        today)
        "parent": ("forbidden", "forbidden", "forbidden"),
        "teacher": ("forbidden", "forbidden", "forbidden"),
        "ananya": ("forbidden", "forbidden", "forbidden"),  # a super admin is not a student
        "student_waiting": ("consent_required", "consent_required", "consent_required"),
        "rohan": ("consent_required", "consent_required", "consent_required"),  # paused
        "student_active": (200, "not_entitled", 200),  # consented, nothing bought
        "kabir": (200, 200, 200),  # programme includes Maths 8
    }

    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", stdout=StringIO())

    def client_for(self, key):
        client = Client()
        client.force_login(
            User.objects.get(mobile=BY_KEY[key].mobile), backend="apps.accounts.backends.EmailOrMobileBackend"
        )
        return client

    def outcome(self, response):
        return response.status_code if response.status_code == 200 else response.json()["error"]["code"]

    def test_matrix(self):
        free = Lesson.objects.get(slug=self.FREE).id
        paid = Lesson.objects.get(slug=self.PAID).id
        for key, expected in self.MATRIX.items():
            client = self.client_for(key)
            actual = (
                self.outcome(client.get(f"/api/v1/lessons/{free}")),
                self.outcome(client.get(f"/api/v1/lessons/{paid}")),
                self.outcome(client.get("/api/v1/student/today")),
            )
            with self.subTest(who=key):
                self.assertEqual(actual, expected)

    def test_quiz_and_finish_follow_the_same_rules(self):
        paid = Lesson.objects.get(slug=self.PAID).id
        for key, expected_code in (
            ("student_active", "not_entitled"),
            ("student_waiting", "consent_required"),
            ("parent", "forbidden"),
        ):
            client = self.client_for(key)
            for path in (f"/api/v1/lessons/{paid}/quiz/start", f"/api/v1/lessons/{paid}/finish"):
                with self.subTest(who=key, path=path):
                    response = client.post(path, data="{}", content_type="application/json")
                    self.assertEqual(response.json()["error"]["code"], expected_code)

    def test_nobody_can_touch_another_students_attempt(self):
        kabir, asha = self.client_for("kabir"), self.client_for("student_active")
        free = Lesson.objects.get(slug=self.FREE).id
        attempt = kabir.post(f"/api/v1/lessons/{free}/quiz/start", data="{}", content_type="application/json").json()[
            "attempt_id"
        ]
        for path, body in (("hint", {"position": 1}), ("answers", {"position": 1, "choice_index": 0}), ("submit", {})):
            with self.subTest(path=path):
                response = asha.post(f"/api/v1/attempts/{attempt}/{path}", data=body, content_type="application/json")
                self.assertEqual(response.status_code, 404)

    def test_parents_act_only_on_their_own_children(self):
        rohan = User.objects.get(mobile=BY_KEY["rohan"].mobile).id
        for key in ("parent", "priya", "kabir"):
            with self.subTest(who=key):
                response = self.client_for(key).post(f"/api/v1/parent/children/{rohan}/consent/restore")
                self.assertEqual(response.status_code, 404)
        self.assertEqual(
            self.client_for("farhan").post(f"/api/v1/parent/children/{rohan}/consent/restore").status_code, 200
        )


@override_settings(TUTOR_DEMO_DATA=True, TUTOR_DEMO_PASSWORD=PASSWORD)
class CsrfTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", stdout=StringIO())

    def test_logged_in_post_needs_the_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(
            User.objects.get(mobile=BY_KEY["kabir"].mobile), backend="apps.accounts.backends.EmailOrMobileBackend"
        )
        lesson = Lesson.objects.get(slug="what-are-rational-numbers").id
        url = f"/api/v1/lessons/{lesson}/finish"
        self.assertEqual(client.post(url).status_code, 403)
        token = client.get("/api/v1/auth/csrf").json()["csrf_token"]
        self.assertEqual(client.post(url, HTTP_X_CSRFTOKEN=token).status_code, 200)
