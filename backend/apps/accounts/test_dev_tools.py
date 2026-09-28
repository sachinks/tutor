"""seed_test_accounts builds exactly the accounts the tester guide promises (docs/testing/tester-guide.md §3)."""

from django.contrib.auth import authenticate
from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.accounts.models import GuardianLink, RoleGrant, User
from apps.accounts.permissions import can_publish_for_lesson
from apps.catalogue.models import Lesson
from apps.commerce.models import Entitlement

from .management.commands.seed_test_accounts import ACCOUNTS, PASSWORD


@override_settings(DEBUG=True, TUTOR_DEV_TOOLS=True)
class SeedTestAccountsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_test_accounts", verbosity=0)

    def user(self, email):
        return User.objects.get(email=email)

    def test_every_account_can_log_in_by_mobile_and_email(self):
        for _, _, mobile, email, _ in ACCOUNTS:
            with self.subTest(email=email):
                self.assertIsNotNone(authenticate(None, username=mobile, password=PASSWORD))
                self.assertIsNotNone(authenticate(None, username=email, password=PASSWORD))

    def test_student_states(self):
        status = {
            e: self.user(e).student_profile.status for e in ("asha@test.tutor", "esha@test.tutor", "wasim@test.tutor")
        }
        self.assertEqual(
            status, {"asha@test.tutor": "active", "esha@test.tutor": "active", "wasim@test.tutor": "awaiting_consent"}
        )

    def test_parent_is_guardian_of_the_active_students_only(self):
        children = set(
            GuardianLink.objects.filter(parent=self.user("parent@test.tutor"), ended_at=None).values_list(
                "student__email", flat=True
            )
        )
        self.assertEqual(children, {"asha@test.tutor", "esha@test.tutor"})

    def test_only_esha_is_enrolled(self):
        enrolled = set(Entitlement.objects.values_list("student__email", flat=True))
        self.assertEqual(enrolled, {"esha@test.tutor"})

    def test_teacher_can_author_and_review_but_not_publish(self):
        tara = self.user("tara@test.tutor")
        self.assertEqual(set(tara.role_grants.values_list("role", flat=True)), {"author", "reviewer"})
        self.assertFalse(can_publish_for_lesson(tara, Lesson.objects.get(slug="what-is-data")))

    def test_lead_can_open_admin_and_publish_ai_foundations(self):
        lalit = self.user("lalit@test.tutor")
        self.assertTrue(lalit.is_staff)
        self.assertFalse(lalit.is_superuser)
        self.assertTrue(lalit.has_perm("content.change_contentversion"))
        self.assertFalse(lalit.has_perm("accounts.change_user"))
        self.assertTrue(can_publish_for_lesson(lalit, Lesson.objects.get(slug="what-is-data")))

    def test_running_again_resets_instead_of_duplicating(self):
        wasim = self.user("wasim@test.tutor")
        wasim.set_password("changed-by-a-tester-1")
        wasim.save()
        call_command("seed_test_accounts", verbosity=0)
        self.assertEqual(User.objects.filter(email__endswith="@test.tutor").count(), len(ACCOUNTS))
        self.assertEqual(RoleGrant.objects.filter(user__email="lalit@test.tutor", revoked_at=None).count(), 1)
        self.assertIsNotNone(authenticate(None, username="wasim@test.tutor", password=PASSWORD))
