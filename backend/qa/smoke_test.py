"""Black-box smoke test over HTTP, in two modes.

Local journey (server running with DJANGO_DEBUG=true and TUTOR_DEV_TOOLS=true):
    python qa/smoke_test.py                       # default http://127.0.0.1:8000
Walks the real journey: catalogue → student sign-up → blocked without consent → parent sign-up and
verification → approval link → lesson → quiz → record/today → consent withdraw/restore.
Uses fresh random mobile numbers, so it can be repeated.

Hosted checks (after every deploy; creates no data, needs no tester tools):
    python qa/smoke_test.py --hosted --base https://tutor-platform-ovlg.onrender.com
Health (waits for a sleeping free-tier service), public catalogue, protected endpoints refuse anonymous
callers, tester tools are off, HTTPS and security headers are in place.

Prints PASS/FAIL per check; exit code 1 on any FAIL.
"""

import argparse
import random
import re
import sys

import requests

PASSWORD = "Smoke-Test-2026"


class Client:
    def __init__(self, base):
        self.base = base.rstrip("/") + "/api/v1"
        self.s = requests.Session()
        self.s.get(self.base + "/auth/csrf", timeout=10)

    def _headers(self):
        return {"X-CSRFToken": self.s.cookies.get("csrftoken", "")}

    def get(self, path, **kw):
        return self.s.get(self.base + path, timeout=15, **kw)

    def post(self, path, json=None):
        return self.s.post(self.base + path, json=json or {}, headers=self._headers(), timeout=15)


results = []


def check(name, condition, detail=""):
    results.append((name, bool(condition)))
    print(f"{'PASS' if condition else 'FAIL'}  {name}" + (f"   ← {detail}" if not condition and detail else ""))
    return bool(condition)


def latest(dev, to, pattern):
    for msg in dev.get("/dev/outbox", params={"to": to}).json():
        m = re.search(pattern, msg["text"])
        if m:
            return m.group(1)
    return None


def hosted_checks(base):
    """Read-only checks for a deployed site. Never signs anyone up, so the hosted data stays clean."""
    api = base.rstrip("/") + "/api/v1"
    s = requests.Session()
    try:
        health = s.get(api + "/health", timeout=90)  # a sleeping free-tier service takes up to a minute to wake
    except requests.RequestException as exc:
        check("H0 site reachable", False, str(exc))
        return
    check(
        "H1 healthy and database reachable",
        health.status_code == 200 and health.json() == {"ok": True, "db": True},
        health.text,
    )
    check("H2 HSTS header present", "max-age=" in health.headers.get("Strict-Transport-Security", ""))
    check("H3 nosniff header present", health.headers.get("X-Content-Type-Options") == "nosniff")

    if base.startswith("https://"):
        plain = requests.get(
            "http://" + base[len("https://") :].rstrip("/") + "/api/v1/catalogue/facets",
            timeout=30,
            allow_redirects=False,
        )
        check(
            "H4 plain HTTP redirects to HTTPS",
            plain.status_code in (301, 308) and plain.headers.get("Location", "").startswith("https://"),
            str(plain.status_code),
        )

    root = s.get(base.rstrip("/") + "/", timeout=30)
    check(
        "H5 root page points to the API docs",
        root.status_code == 200 and root.json().get("docs") == "/api/v1/docs",
        root.text[:200],
    )

    csrf = s.get(api + "/auth/csrf", timeout=30)
    cookie = next((c for c in s.cookies if c.name == "csrftoken"), None)
    check("H6 CSRF cookie is Secure", csrf.status_code == 200 and cookie is not None and cookie.secure)

    items = s.get(api + "/catalogue/items", timeout=30).json()["results"]
    check("C1 catalogue lists AI Foundations", any(i["slug"] == "ai-foundations" for i in items))
    course = s.get(api + "/courses/ai-foundations", timeout=30).json()
    lessons = [lesson for m in course["modules"] for lesson in m["lessons"]]
    check("C2 course has lessons and skills", len(lessons) >= 1 and len(course["skills"]) >= 1)
    free = next((lesson for lesson in lessons if lesson["is_free"]), None)
    if check("C3 course has a free lesson", free is not None):
        r = s.get(api + f"/lessons/{free['id']}/preview", timeout=30)
        check(
            "C4 free lesson preview readable without login", r.status_code == 200 and r.json()["sections"], r.text[:200]
        )
    check("C5 unknown course is 404", s.get(api + "/courses/does-not-exist", timeout=30).status_code == 404)

    anon = requests.Session()
    for path in ("/me", "/student/today", "/student/record"):
        r = anon.get(api + path, timeout=30)
        check(f"X1 anonymous {path} is 401", r.status_code == 401, r.text[:200])
    if lessons:
        check(
            "X2 anonymous lesson is 401", anon.get(api + f"/lessons/{lessons[0]['id']}", timeout=30).status_code == 401
        )
    check("X3 tester tools are off", anon.get(api + "/dev/outbox", timeout=30).status_code == 404)
    # A made-up address, so no real account moves toward the login lockout.
    anon.get(api + "/auth/csrf", timeout=30)
    r = anon.post(
        api + "/auth/login",
        json={"identifier": f"smoke-{random.randint(10**6, 10**7)}@example.invalid", "password": "wrong-password"},
        headers={"X-CSRFToken": anon.cookies.get("csrftoken", ""), "Referer": base},
        timeout=30,
    )
    check(
        "X4 wrong login is refused cleanly",
        r.status_code == 400 and r.json()["error"]["code"] == "invalid_credentials",
        r.text[:200],
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--hosted", action="store_true", help="read-only checks for a deployed site")
    args = ap.parse_args()
    if args.hosted:
        hosted_checks(args.base)
        return
    student_mobile = f"98{random.randint(10**7, 10**8 - 1)}"
    parent_mobile = f"97{random.randint(10**7, 10**8 - 1)}"
    student, parent, dev = Client(args.base), Client(args.base), Client(args.base)

    check("S0 server healthy", dev.get("/health").json().get("ok") is True)
    if not check(
        "S0 dev tools enabled",
        dev.get("/dev/outbox").status_code == 200,
        "set DJANGO_DEBUG=true and TUTOR_DEV_TOOLS=true in .env, restart the server",
    ):
        return

    items = dev.get("/catalogue/items").json()["results"]
    check("C1 catalogue lists AI Foundations", any(i["slug"] == "ai-foundations" for i in items))
    course = dev.get("/courses/ai-foundations").json()
    lessons = [lesson for m in course["modules"] for lesson in m["lessons"]]
    check("C2 course has lessons and skills", len(lessons) >= 1 and len(course["skills"]) >= 1)
    lesson_id = lessons[0]["id"]

    r = student.post(
        "/auth/signup/student",
        {
            "full_name": "Smoke Student",
            "mobile": student_mobile,
            "password": PASSWORD,
            "class_number": 8,
            "board_code": "CBSE",
            "city": "Kolkata",
            "parent_contact": parent_mobile,
        },
    )
    check(
        "A1 student sign-up → awaiting consent",
        r.status_code == 201 and r.json()["student"]["status"] == "awaiting_consent",
        r.text,
    )
    r = student.get(f"/lessons/{lesson_id}")
    check(
        "A2 lesson blocked before consent",
        r.status_code == 403 and r.json()["error"]["code"] == "consent_required",
        r.text,
    )

    token = latest(dev, "+91" + parent_mobile, r"/approve/([A-Za-z0-9_-]+)")
    check("A3 parent received approval link", token is not None)

    r = parent.post("/auth/signup/parent", {"full_name": "Smoke Parent", "mobile": parent_mobile, "password": PASSWORD})
    check("A4 parent sign-up", r.status_code == 201, r.text)
    code = latest(dev, "+91" + parent_mobile, r"code is (\d{6})")
    r = parent.post("/auth/otp/verify", {"destination": parent_mobile, "purpose": "verify_contact", "code": code})
    check("A5 parent verifies mobile", r.status_code == 200 and r.json()["mobile_verified"], r.text)

    r = parent.get(f"/consent/link/{token}")
    check(
        "A6 approval page shows child and consent text",
        r.status_code == 200 and r.json()["child_first_name"] == "Smoke",
        r.text,
    )
    r = parent.post(f"/consent/link/{token}/approve", {"relationship": "mother", "accept": True})
    check("A7 parent approves", r.status_code == 200, r.text)
    check("A8 student now active", student.get("/me").json()["student"]["status"] == "active")

    r = student.get(f"/lessons/{lesson_id}")
    check("L1 student opens free lesson", r.status_code == 200 and len(r.json()["sections"]) >= 1, r.text)
    r = student.post(f"/lessons/{lesson_id}/quiz/start")
    ok = check("Q1 quiz starts without leaking answers", r.status_code == 200 and "answer_index" not in r.text, r.text)
    if ok:
        attempt = r.json()
        aid = attempt["attempt_id"]
        r = student.post(f"/attempts/{aid}/hint", {"position": 1})
        check("Q2 hint returned", r.status_code == 200 and r.json()["hint"], r.text)
        for item in attempt["items"]:
            r = student.post(f"/attempts/{aid}/answers", {"position": item["position"], "choice_index": 0})
            check(
                f"Q3 answer question {item['position']} gets feedback",
                r.status_code == 200 and "explanation" in r.json(),
                r.text,
            )
        r = student.post(f"/attempts/{aid}/answers", {"position": 1, "choice_index": 1})
        check("Q4 answering twice is refused", r.status_code == 409, r.text)
        r = student.post(f"/attempts/{aid}/submit")
        check("Q5 submit returns score and skill changes", r.status_code == 200 and r.json()["skill_changes"], r.text)

    record = student.get("/student/record").json()
    check("R1 record shows the quiz and mastery", record["quizzes"] and record["mastery"])
    check("R2 today responds", student.get("/student/today").status_code == 200)

    child_id = student.get("/me").json()["id"]
    check(
        "P1 parent withdraws consent", parent.post(f"/parent/children/{child_id}/consent/withdraw").status_code == 200
    )
    r = student.get(f"/lessons/{lesson_id}")
    check(
        "P2 lesson blocked after withdrawal",
        r.status_code == 403 and r.json()["error"]["code"] == "consent_required",
        r.text,
    )
    check("P3 parent restores consent", parent.post(f"/parent/children/{child_id}/consent/restore").status_code == 200)
    check("P4 lesson open again", student.get(f"/lessons/{lesson_id}").status_code == 200)

    outsider = Client(args.base)
    check("X1 anonymous /me is 401", outsider.get("/me").status_code == 401)
    check("X2 unknown course is 404", outsider.get("/courses/does-not-exist").status_code == 404)


if __name__ == "__main__":
    try:
        main()
    except requests.ConnectionError:
        print("FAIL  cannot reach the server — is `python manage.py runserver` running?")
        sys.exit(1)
    failed = [name for name, ok in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed.")
    sys.exit(1 if failed else 0)
