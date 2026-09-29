"""Boundary values and malformed input: every bad request is a clean 400 with the field named, never a 500."""

from django.test import Client

from apps.accounts.models import User

from .test_api import STUDENT, ApiTestCase, last_message_to, link_token, post


class SignupBoundaryTests(ApiTestCase):
    def assertFieldError(self, overrides, field, path="/auth/signup/student", base=STUDENT):
        res = post(Client(), path, {**base, **overrides})
        self.assertEqual(res.status_code, 400, res.content)
        body = res.json()["error"]
        self.assertEqual(body["code"], "validation_error")
        self.assertIn(field, body["fields"], body)

    def test_text_fields_are_limited_to_the_database_columns(self):
        for field, value in (
            ("full_name", "x" * 151),
            ("city", "c" * 81),
            ("school_name", "s" * 151),
            ("email", "a" * 250 + "@x.in"),
            ("parent_contact", "9" * 300),
        ):
            with self.subTest(field=field):
                self.assertFieldError({field: value}, field)

    def test_blank_and_whitespace_names_are_refused(self):
        for value in ("", "   "):
            with self.subTest(value=repr(value)):
                self.assertFieldError({"full_name": value}, "full_name")

    def test_longest_allowed_values_are_accepted(self):
        res = post(Client(), "/auth/signup/student", {**STUDENT, "full_name": "N" * 150, "city": "C" * 80})
        self.assertEqual(res.status_code, 201, res.content)

    def test_class_range_edges(self):
        for number, ok in ((5, False), (6, True), (12, True), (13, False)):
            with self.subTest(class_number=number):
                data = {
                    **STUDENT,
                    "class_number": number,
                    "mobile": f"98000100{number:02d}",
                    "parent_contact": f"97000100{number:02d}",
                }
                res = post(Client(), "/auth/signup/student", data)
                self.assertEqual(res.status_code, 201 if ok else 400, res.content)

    def test_wrong_types_and_unknown_board(self):
        self.assertFieldError({"class_number": "eight"}, "class_number")
        self.assertFieldError({"board_code": "XYZ"}, "board_code")

    def test_passwords(self):
        self.assertFieldError({"password": "p" * 129}, "password")  # hashing cap
        self.assertFieldError({"password": "12345678"}, "password")  # numeric / common

    def test_mobile_formats(self):
        for mobile, ok in (
            ("98000 20001", True),
            ("+91 98000 20002", True),
            ("919800020003", True),
            ("12345", False),
            ("98000abcde", False),
        ):
            with self.subTest(mobile=mobile):
                res = post(
                    Client(), "/auth/signup/student", {**STUDENT, "mobile": mobile, "parent_contact": "9700029999"}
                )
                self.assertEqual(res.status_code == 201, ok, res.content)

    def test_huge_login_password_is_refused_before_hashing(self):
        res = post(Client(), "/auth/login", {"identifier": "someone@example.com", "password": "p" * 10_000})
        self.assertEqual(res.status_code, 400)
        self.assertIn("password", res.json()["error"]["fields"])

    def test_malformed_json_is_a_400(self):
        res = Client().post("/api/v1/auth/login", data="{not json", content_type="application/json")
        self.assertEqual(res.status_code, 400)


class AccountFlowGapTests(ApiTestCase):
    """Manual cases TC-ACC-07, TC-CON-04, TC-SEC-03 and TC-SEC-12, automated."""

    def test_logout(self):
        self.signup_student()
        self.assertEqual(post(self.student_client, "/auth/logout").status_code, 200)
        self.assertEqual(self.student_client.get("/api/v1/me").status_code, 401)

    def test_consent_box_must_be_ticked(self):
        self.signup_student()
        token = link_token(last_message_to("+919800000002"))
        self.signup_verified_parent()
        res = post(self.parent_client, f"/consent/link/{token}/approve", {"relationship": "mother", "accept": False})
        self.assertEqual(res.status_code, 400)
        self.assertIn("accept", res.json()["error"]["fields"])

    def test_student_cannot_approve_own_account(self):
        self.signup_student()
        token = link_token(last_message_to("+919800000002"))
        res = post(self.student_client, f"/consent/link/{token}/approve", {"relationship": "mother", "accept": True})
        self.assertEqual(res.status_code, 403)
        self.assertEqual(self.student_client.get("/api/v1/me").json()["student"]["status"], "awaiting_consent")

    def test_data_minimisation(self):
        me = self.signup_student()
        token = link_token(last_message_to("+919800000002"))
        page = Client().get(f"/api/v1/consent/link/{token}").json()
        text = str(page).lower() + str(me).lower()
        for forbidden in ("birth", "dob", "date_of_birth"):
            self.assertNotIn(forbidden, text)
        self.assertEqual(page["child_first_name"], "Riya")
        self.assertNotIn("Sen", str(page))  # surname never shown to whoever holds the link


class AdminFormTests(ApiTestCase):
    def test_admin_user_creation_needs_a_contact_and_a_strong_password(self):
        superuser = User.objects.create_superuser(email="su@example.com", password="x-long-pass-1", full_name="Su")
        client = Client()
        client.force_login(superuser)
        base = {
            "full_name": "New Person",
            "account_type": "parent",
            "password1": "Strong-pass-2026",
            "password2": "Strong-pass-2026",
        }
        res = client.post("/admin/accounts/user/add/", {**base, "email": "", "mobile": ""})
        self.assertEqual(res.status_code, 200)  # form shown again with the error
        self.assertContains(res, "Enter an email or a mobile number.")
        res = client.post(
            "/admin/accounts/user/add/",
            {**base, "mobile": "+919811100001", "password1": "12345678", "password2": "12345678"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertFalse(User.objects.filter(mobile="+919811100001").exists())
        res = client.post("/admin/accounts/user/add/", {**base, "mobile": "+919811100002", "email": ""})
        self.assertEqual(res.status_code, 302)
        self.assertTrue(User.objects.filter(mobile="+919811100002").exists())

    def test_admin_user_search(self):
        self.signup_student()
        superuser = User.objects.create_superuser(email="su@example.com", password="x-long-pass-1", full_name="Su")
        client = Client()
        client.force_login(superuser)
        for query in ("Riya", "9800000001"):
            with self.subTest(query=query):
                self.assertContains(client.get("/admin/accounts/user/", {"q": query}), "Riya Sen")
