"""Brute-force protection (quality backlog Q3): rate limits, login lockout and trusted client IPs."""

from django.core.cache import cache
from django.test import Client, RequestFactory, SimpleTestCase, override_settings

from apps.core.http import client_ip
from apps.core.throttling import parse_rate

from . import lockout
from .test_api import STUDENT, ApiTestCase, last_message_to, otp, post

LOCKOUT = {"max_failures": 3, "window_seconds": 900}


class ParseRateTests(SimpleTestCase):
    def test_valid_rates(self):
        self.assertEqual(parse_rate("30/m"), (30, 60))
        self.assertEqual(parse_rate("10/h"), (10, 3600))
        self.assertEqual(parse_rate("5/10m"), (5, 600))
        self.assertEqual(parse_rate("1/d"), (1, 86400))

    def test_invalid_rates(self):
        for rate in ("", "30", "30/x", "abc/m", "0/m", "5/0m"):
            with self.subTest(rate=rate), self.assertRaises(ValueError):
                parse_rate(rate)


class ClientIpTests(SimpleTestCase):
    def request(self, xff=None):
        extra = {"REMOTE_ADDR": "10.0.0.1"}
        if xff is not None:
            extra["HTTP_X_FORWARDED_FOR"] = xff
        return RequestFactory().get("/", **extra)

    @override_settings(TUTOR_TRUSTED_PROXIES=0)
    def test_header_ignored_without_trusted_proxies(self):
        self.assertEqual(client_ip(self.request("1.2.3.4")), "10.0.0.1")

    @override_settings(TUTOR_TRUSTED_PROXIES=1)
    def test_forged_left_entries_are_ignored(self):
        # The client sent "6.6.6.6"; Render appended the real address it saw.
        self.assertEqual(client_ip(self.request("6.6.6.6, 203.0.113.9")), "203.0.113.9")

    @override_settings(TUTOR_TRUSTED_PROXIES=2)
    def test_two_proxies(self):
        self.assertEqual(client_ip(self.request("6.6.6.6, 203.0.113.9, 10.1.1.1")), "203.0.113.9")

    @override_settings(TUTOR_TRUSTED_PROXIES=1)
    def test_no_header_falls_back_to_remote_addr(self):
        self.assertEqual(client_ip(self.request()), "10.0.0.1")
        self.assertEqual(client_ip(self.request(" , ")), "10.0.0.1")


class RateLimitTests(ApiTestCase):
    def login(self, client, password="wrong-password", identifier="someone@example.com"):
        return post(client, "/auth/login", {"identifier": identifier, "password": password})

    @override_settings(TUTOR_THROTTLE_RATES={"login": "3/m"})
    def test_login_is_rate_limited_per_ip(self):
        client = Client()
        for _ in range(3):
            self.assertEqual(self.login(client).status_code, 400)
        res = self.login(client)
        self.assertEqual(res.status_code, 429)
        self.assertEqual(res.json()["error"]["code"], "limit_reached")
        self.assertGreaterEqual(int(res["Retry-After"]), 1)

    @override_settings(TUTOR_THROTTLE_RATES={"login": "2/m"}, TUTOR_TRUSTED_PROXIES=1)
    def test_limit_is_per_client_ip(self):
        a = Client(HTTP_X_FORWARDED_FOR="198.51.100.1")
        b = Client(HTTP_X_FORWARDED_FOR="198.51.100.2")
        self.login(a)
        self.login(a)
        self.assertEqual(self.login(a).status_code, 429)
        self.assertEqual(self.login(b).status_code, 400)

    @override_settings(TUTOR_THROTTLE_RATES={"login": "2/m"}, TUTOR_TRUSTED_PROXIES=1)
    def test_forging_x_forwarded_for_does_not_escape_the_limit(self):
        for n in range(2):
            self.login(Client(HTTP_X_FORWARDED_FOR=f"6.6.6.{n}, 198.51.100.1"))
        res = self.login(Client(HTTP_X_FORWARDED_FOR="6.6.6.9, 198.51.100.1"))
        self.assertEqual(res.status_code, 429)

    @override_settings(TUTOR_THROTTLE_RATES={"signup": "1/h"})
    def test_signup_is_rate_limited(self):
        self.signup_student()
        other = dict(STUDENT, mobile="9800000011", parent_contact="9800000012")
        self.assertEqual(post(Client(), "/auth/signup/student", other).status_code, 429)

    @override_settings(TUTOR_THROTTLE_RATES={"otp": "2/h"})
    def test_one_time_code_endpoints_are_rate_limited(self):
        client = Client()
        body = {"destination": "9811111111", "purpose": "login"}
        post(client, "/auth/otp/send", body)
        post(client, "/auth/otp/send", body)
        self.assertEqual(post(client, "/auth/otp/send", body).status_code, 429)

    @override_settings(TUTOR_THROTTLE_RATES={"consent_link": "2/h"})
    def test_consent_link_pages_are_rate_limited(self):
        client = Client()
        for _ in range(2):
            self.assertEqual(client.get("/api/v1/consent/link/not-a-real-token").status_code, 404)
        self.assertEqual(client.get("/api/v1/consent/link/not-a-real-token").status_code, 429)

    @override_settings(TUTOR_THROTTLE_RATES={"api": "3/m"})
    def test_general_ceiling_applies_to_every_endpoint(self):
        client = Client()
        for _ in range(3):
            self.assertEqual(client.get("/api/v1/catalogue/facets").status_code, 200)
        self.assertEqual(client.get("/api/v1/catalogue/facets").status_code, 429)

    def test_no_rate_configured_means_no_limit(self):
        client = Client()  # test settings switch every rate off
        # A different account each time, so the per-account lockout (10 failures) doesn't kick in instead.
        for n in range(20):
            self.assertEqual(self.login(client, identifier=f"someone{n}@example.com").status_code, 400)


@override_settings(TUTOR_LOGIN_LOCKOUT=LOCKOUT)
class LoginLockoutTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.signup_student()

    def login(self, password, identifier="9800000001"):
        return post(Client(), "/auth/login", {"identifier": identifier, "password": password})

    def test_account_locks_after_repeated_wrong_passwords(self):
        self.assertEqual(self.login("wrong-1").status_code, 400)
        self.assertEqual(self.login("wrong-2").status_code, 400)
        res = self.login("wrong-3")
        self.assertEqual(res.status_code, 429)
        self.assertEqual(res.json()["error"]["code"], "login_locked")
        # Even the right password is refused while locked.
        self.assertEqual(self.login(STUDENT["password"]).json()["error"]["code"], "login_locked")

    def test_successful_login_resets_the_count(self):
        self.login("wrong-1")
        self.login("wrong-2")
        self.assertEqual(self.login(STUDENT["password"]).status_code, 200)
        self.assertEqual(lockout.failures("+919800000001"), 0)
        self.assertEqual(self.login("wrong-3").status_code, 400)

    def test_unknown_accounts_lock_the_same_way(self):
        """The lockout mustn't reveal which emails or mobiles have accounts."""
        for n in range(2):
            self.assertEqual(self.login(f"x{n}", identifier="nobody@example.com").status_code, 400)
        self.assertEqual(self.login("x3", identifier="nobody@example.com").status_code, 429)

    def test_lockout_is_per_account(self):
        for n in range(3):
            self.login(f"wrong-{n}")
        self.assertEqual(self.login("x", identifier="nobody@example.com").status_code, 400)

    def test_password_reset_lifts_the_lockout(self):
        for n in range(3):
            self.login(f"wrong-{n}")
        post(Client(), "/auth/otp/send", {"destination": "9800000001", "purpose": "reset_password"})
        code = otp(last_message_to("+919800000001"))
        res = post(
            Client(),
            "/auth/password/reset",
            {"destination": "9800000001", "code": code, "new_password": "Brand-new-2026"},
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(self.login("Brand-new-2026").status_code, 200)

    def test_lockout_also_protects_the_admin_login(self):
        from django.contrib.auth import authenticate

        for n in range(3):
            self.login(f"wrong-{n}")
        self.assertEqual(lockout.failures("+919800000001"), 3)
        self.assertIsNone(authenticate(None, username="+919800000001", password=STUDENT["password"]))

    def test_lockout_expires(self):
        for n in range(3):
            self.login(f"wrong-{n}")
        cache.clear()  # stands in for the window passing
        self.assertEqual(self.login(STUDENT["password"]).status_code, 200)
