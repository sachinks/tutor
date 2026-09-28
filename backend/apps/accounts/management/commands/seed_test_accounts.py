"""Ready-made accounts for testers (docs/testing/tester-guide.md). Refuses to run unless DEBUG and TUTOR_DEV_TOOLS.

All passwords: Test-Pass-2026   (never use these on a shared or production server)
"""

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import (
    ConsentRecord,
    ConsentText,
    GuardianLink,
    ParentProfile,
    RoleGrant,
    StudentProfile,
    TeacherProfile,
    User,
)
from apps.catalogue.models import Board, ClassLevel, Course, Subject
from apps.commerce.models import Entitlement

PASSWORD = "Test-Pass-2026"

ACCOUNTS = [
    # key, full name, mobile, email, kind
    ("parent", "Test Parent", "+919000000001", "parent@test.tutor", "parent"),
    ("student_active", "Asha Active", "+919000000002", "asha@test.tutor", "student"),
    ("student_enrolled", "Esha Enrolled", "+919000000003", "esha@test.tutor", "student"),
    ("student_waiting", "Wasim Waiting", "+919000000004", "wasim@test.tutor", "student"),
    ("teacher", "Tara Teacher", "+919000000005", "tara@test.tutor", "teacher"),
]


class Command(BaseCommand):
    help = "Create or reset tester accounts with known passwords (local development only)."

    @transaction.atomic
    def handle(self, *args, **options):
        if not (settings.DEBUG and getattr(settings, "TUTOR_DEV_TOOLS", False)):
            raise CommandError("Refusing: needs DJANGO_DEBUG=true and TUTOR_DEV_TOOLS=true (local development only).")
        call_command("seed_reference", verbosity=0)
        call_command("seed_consent", verbosity=0)
        call_command("seed_demo_catalogue", verbosity=0)

        now = timezone.now()
        users = {}
        for key, name, mobile, email, kind in ACCOUNTS:
            user, _ = User.objects.get_or_create(
                mobile=mobile, defaults={"full_name": name, "email": email, "account_type": kind}
            )
            user.full_name, user.email, user.account_type = name, email, kind
            user.mobile_verified_at = user.email_verified_at = now
            user.is_active, user.deleted_at = True, None
            user.set_password(PASSWORD)
            user.save()
            users[key] = user

        ParentProfile.objects.get_or_create(user=users["parent"])
        class8, cbse = ClassLevel.objects.get(number=8), Board.objects.get(code="CBSE")
        text = ConsentText.current()
        for key, status in [
            ("student_active", "active"),
            ("student_enrolled", "active"),
            ("student_waiting", "awaiting_consent"),
        ]:
            profile, _ = StudentProfile.objects.get_or_create(
                user=users[key], defaults={"class_level": class8, "board": cbse, "city": "Kolkata"}
            )
            profile.status = status
            profile.save()
            if status == "active":
                link, _ = GuardianLink.objects.get_or_create(
                    parent=users["parent"], student=users[key], ended_at=None, defaults={"relationship": "mother"}
                )
                if not link.consents.filter(withdrawn_at__isnull=True).exists():
                    ConsentRecord.objects.create(guardian_link=link, consent_text=text, given_ip="127.0.0.1")

        course = Course.objects.get(slug="ai-foundations")
        Entitlement.objects.get_or_create(
            student=users["student_enrolled"],
            product_type="course",
            product_id=course.id,
            revoked_at=None,
            defaults={"source": "admin_grant"},
        )

        TeacherProfile.objects.get_or_create(user=users["teacher"], defaults={"display_name": "Tara Teacher"})
        ai = Subject.objects.get(slug="ai-foundations")
        for role in ("author", "reviewer"):
            RoleGrant.objects.get_or_create(
                user=users["teacher"], role=role, subject=ai, class_level=None, revoked_at=None
            )

        if options.get("verbosity", 1) > 0:
            self.stdout.write(self.style.SUCCESS("Test accounts ready (password for all: Test-Pass-2026):"))
            for key, name, mobile, email, _ in ACCOUNTS:
                self.stdout.write(f"  {key:<17} {name:<15} {mobile}  {email}")
