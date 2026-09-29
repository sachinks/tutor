"""Personal tester accounts: one clean student per tester, so testers don't overwrite each other's quizzes,
mastery and streaks on the shared demo.

Each tester is an active (parent-approved) Class 8 CBSE student enrolled in every published course. A system
"Tester Guardian" parent (no usable password) gives the consent. Passwords are random, returned once to the caller
and stored only as hashes. Emails use the non-existent test.tutor domain; mobiles the +91 90000 009xx range.
"""

import secrets
from dataclasses import dataclass

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import ConsentRecord, ConsentText, GuardianLink, ParentProfile, StudentProfile, User
from apps.catalogue.models import Board, ClassLevel, Course, PublishStatus
from apps.commerce.models import Entitlement

GUARDIAN = {"email": "tester-guardian@test.tutor", "mobile": "+919000000900", "name": "Tester Guardian"}
MAX_TESTERS = 99


@dataclass(frozen=True)
class TesterCredential:
    number: int
    name: str
    email: str
    mobile: str
    password: str | None  # None when the account already existed and its password was kept
    created: bool


def tester_identity(number):
    return f"Tester {number}", f"tester{number}@test.tutor", f"+919000000{900 + number}"


def generate_password():
    """16 random URL-safe characters (~96 bits); retried until it passes the site's password rules."""
    while True:
        candidate = secrets.token_urlsafe(12)
        try:
            validate_password(candidate)
        except ValidationError:
            continue  # noqa: S112 - a rare weak draw (e.g. all digits); nothing to log, just draw again
        return candidate


def _guardian(now):
    user = User.objects.filter(email=GUARDIAN["email"]).first()
    if user is None:
        user = User(
            email=GUARDIAN["email"], mobile=GUARDIAN["mobile"], full_name=GUARDIAN["name"], account_type="parent"
        )
        user.set_unusable_password()
    user.email_verified_at = user.mobile_verified_at = now
    user.save()
    ParentProfile.objects.get_or_create(user=user)
    return user


@transaction.atomic
def ensure_testers(count, reset_passwords=False):
    if not 1 <= count <= MAX_TESTERS:
        raise ValueError(f"count must be between 1 and {MAX_TESTERS}")
    now = timezone.now()
    guardian = _guardian(now)
    text = ConsentText.current()
    class8, cbse = ClassLevel.objects.get(number=8), Board.objects.get(code="CBSE")
    courses = list(Course.objects.filter(status=PublishStatus.PUBLISHED).values_list("id", flat=True))
    results = []
    for number in range(1, count + 1):
        name, email, mobile = tester_identity(number)
        user = User.objects.filter(email=email).first()
        created = user is None
        password = None
        if created:
            user = User(email=email, mobile=mobile, full_name=name, account_type="student")
        if created or reset_passwords:
            password = generate_password()
            user.set_password(password)
        user.is_active, user.deleted_at = True, None
        user.email_verified_at = user.mobile_verified_at = now
        user.save()
        profile, _ = StudentProfile.objects.get_or_create(
            user=user, defaults={"class_level": class8, "board": cbse, "city": "Kolkata"}
        )
        if profile.status != StudentProfile.Status.ACTIVE:
            profile.status = StudentProfile.Status.ACTIVE
            profile.save(update_fields=["status", "updated_at"])
        link, _ = GuardianLink.objects.get_or_create(
            parent=guardian, student=user, ended_at=None, defaults={"relationship": "guardian"}
        )
        if not link.consents.filter(withdrawn_at__isnull=True).exists():
            ConsentRecord.objects.create(guardian_link=link, consent_text=text, given_ip="127.0.0.1")
        for course_id in courses:
            Entitlement.objects.get_or_create(
                student=user,
                product_type="course",
                product_id=course_id,
                revoked_at=None,
                defaults={"source": "admin_grant"},
            )
        results.append(TesterCredential(number, name, email, mobile, password, created))
    return results
