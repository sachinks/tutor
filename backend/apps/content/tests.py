"""Who may publish (quality backlog Q4, decision D19), through services and through the admin."""

from django.contrib.admin.sites import site
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.forms import modelform_factory
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.accounts.models import RoleGrant, User
from apps.assessment import services as assessment_services
from apps.assessment.models import Question, QuestionVersion
from apps.catalogue.models import ClassLevel, Course, Lesson, Module, PublishStatus, Skill, Subject
from apps.core.admin_guards import VersionStatusForm
from apps.core.errors import ApiError
from apps.operations.models import AuditLog

from . import services
from .models import ContentVersion


def make_user(email, **extra):
    return User.objects.create_user(email=email, password="x-long-pass-1", full_name=email.split("@")[0], **extra)


class PublishingFixtures(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo_catalogue", verbosity=0)
        cls.maths = Subject.objects.get(slug="mathematics")
        cls.ai = Subject.objects.get(slug="ai-foundations")
        cls.class8, cls.class9 = ClassLevel.objects.get(number=8), ClassLevel.objects.get(number=9)
        cls.maths8_lesson = cls.make_lesson("maths-8", cls.class8)
        cls.maths9_lesson = cls.make_lesson("maths-9", cls.class9)
        cls.ai_lesson = Lesson.objects.get(slug="what-is-data")  # AI Foundations: no class
        cls.author = make_user("author@example.com")
        cls.reviewer = make_user("reviewer@example.com")

    @classmethod
    def make_lesson(cls, slug, class_level):
        course = Course.objects.create(
            subject=cls.maths, class_level=class_level, title=slug, slug=slug, status=PublishStatus.PUBLISHED
        )
        module = Module.objects.create(course=course, title="Numbers", position=1)
        return Lesson.objects.create(module=module, title=f"{slug} lesson", slug=f"{slug}-lesson", position=1)

    def approved(self, lesson):
        return ContentVersion.objects.create(
            lesson=lesson,
            version_no=services.next_version_no(lesson),
            body={"sections": []},
            status=ContentVersion.Status.APPROVED,
            author=self.author,
            reviewer=self.reviewer,
        )

    def lead(self, email, subject=None, class_level=None, **grant):
        user = make_user(email)
        RoleGrant.objects.create(
            user=user, role=RoleGrant.Role.CURRICULUM_LEAD, subject=subject, class_level=class_level, **grant
        )
        return user

    def assertCanPublish(self, user, lesson):
        version = services.publish(self.approved(lesson), user)
        self.assertEqual(version.status, ContentVersion.Status.PUBLISHED)
        self.assertEqual(version.published_by, user)

    def assertCannotPublish(self, user, lesson):
        version = self.approved(lesson)
        with self.assertRaises(ApiError) as ctx:
            services.publish(version, user)
        self.assertEqual((ctx.exception.status, ctx.exception.code), (403, "forbidden"))
        version.refresh_from_db()
        self.assertEqual(version.status, ContentVersion.Status.APPROVED)


class PublishPermissionTests(PublishingFixtures):
    def test_reviewer_without_lead_role_cannot_publish(self):
        self.assertCannotPublish(self.reviewer, self.maths8_lesson)

    def test_staff_flag_alone_is_not_enough(self):
        self.assertCannotPublish(make_user("staff@example.com", is_staff=True), self.maths8_lesson)

    def test_lead_for_subject_and_class(self):
        lead = self.lead("m8@example.com", self.maths, self.class8)
        self.assertCanPublish(lead, self.maths8_lesson)
        self.assertCannotPublish(lead, self.maths9_lesson)
        self.assertCannotPublish(lead, self.ai_lesson)

    def test_subject_wide_lead_covers_every_class(self):
        lead = self.lead("m@example.com", self.maths)
        self.assertCanPublish(lead, self.maths8_lesson)
        self.assertCanPublish(lead, self.maths9_lesson)

    def test_class_scoped_lead_does_not_own_board_independent_courses(self):
        self.assertCannotPublish(self.lead("ai8@example.com", self.ai, self.class8), self.ai_lesson)
        self.assertCanPublish(self.lead("ai@example.com", self.ai), self.ai_lesson)

    def test_revoked_grant(self):
        self.assertCannotPublish(
            self.lead("old@example.com", self.maths, revoked_at=timezone.now()), self.maths8_lesson
        )

    def test_other_roles_do_not_publish(self):
        user = make_user("ops@example.com")
        RoleGrant.objects.create(user=user, role=RoleGrant.Role.OPERATIONS)
        self.assertCannotPublish(user, self.maths8_lesson)

    def test_inactive_lead(self):
        lead = self.lead("gone@example.com", self.maths)
        lead.is_active = False
        lead.save()
        self.assertCannotPublish(lead, self.maths8_lesson)

    def test_super_admins(self):
        self.assertCanPublish(
            User.objects.create_superuser(email="su@example.com", password="x-long-pass-1", full_name="Super"),
            self.maths8_lesson,
        )
        admin = make_user("sa@example.com")
        RoleGrant.objects.create(user=admin, role=RoleGrant.Role.SUPER_ADMIN)
        self.assertCanPublish(admin, self.maths9_lesson)

    def test_question_publishing_follows_the_same_rule(self):
        skill = Skill.objects.get(code="AI-DATA-01")
        question = Question.objects.create(lesson=self.maths8_lesson, skill=skill)

        def approved_question():
            return QuestionVersion.objects.create(
                question=question,
                version_no=assessment_services.next_question_version_no(question),
                body={"stem": "?", "options": ["a", "b"], "answer_index": 0},
                status=QuestionVersion.Status.APPROVED,
                author=self.author,
                reviewer=self.reviewer,
            )

        with self.assertRaises(ApiError):
            assessment_services.publish_question_version(approved_question(), self.reviewer)
        lead = self.lead("q@example.com", self.maths, self.class8)
        self.assertEqual(assessment_services.publish_question_version(approved_question(), lead).status, "published")

    def test_bank_question_without_a_lesson_needs_a_super_admin(self):
        question = Question.objects.create(lesson=None, skill=Skill.objects.get(code="AI-DATA-01"))
        version = QuestionVersion.objects.create(
            question=question, version_no=1, body={}, status="approved", author=self.author, reviewer=self.reviewer
        )
        with self.assertRaises(ApiError):
            assessment_services.publish_question_version(version, self.lead("any@example.com"))


class AdminPublishingTests(PublishingFixtures):
    CHANGELIST = "/admin/content/contentversion/"

    def staff(self, email, lead_subject=None):
        user = make_user(email, is_staff=True)
        user.user_permissions.set(
            Permission.objects.filter(
                content_type__app_label="content", codename__in=["view_contentversion", "change_contentversion"]
            )
        )
        if lead_subject:
            RoleGrant.objects.create(user=user, role=RoleGrant.Role.CURRICULUM_LEAD, subject=lead_subject)
        self.client.force_login(user)
        return user

    def run_publish_action(self, version):
        return self.client.post(
            self.CHANGELIST, {"action": "publish_selected", "_selected_action": [str(version.pk)]}, follow=True
        )

    def test_staff_without_role_is_refused(self):
        self.staff("staff@example.com")
        version = self.approved(self.maths8_lesson)
        res = self.run_publish_action(version)
        self.assertContains(res, "Only the curriculum lead")
        version.refresh_from_db()
        self.assertEqual(version.status, "approved")

    def test_lead_publishes_and_it_is_audited(self):
        lead = self.staff("lead@example.com", lead_subject=self.maths)
        version = self.approved(self.maths8_lesson)
        res = self.run_publish_action(version)
        self.assertContains(res, "Published 1 version(s).")
        version.refresh_from_db()
        self.assertEqual((version.status, version.published_by), ("published", lead))
        self.assertTrue(
            AuditLog.objects.filter(action="content.published", object_id=str(version.pk), actor=lead).exists()
        )

    def test_question_publish_action(self):
        user = make_user("qlead@example.com", is_staff=True)
        user.user_permissions.set(
            Permission.objects.filter(content_type__app_label="assessment", codename__endswith="questionversion")
        )
        RoleGrant.objects.create(user=user, role=RoleGrant.Role.CURRICULUM_LEAD, subject=self.maths)
        self.client.force_login(user)
        question = Question.objects.create(lesson=self.maths8_lesson, skill=Skill.objects.get(code="AI-DATA-01"))
        mine, other = (
            QuestionVersion.objects.create(
                question=q, version_no=1, body={}, status="approved", author=self.author, reviewer=self.reviewer
            )
            for q in (question, Question.objects.create(lesson=self.ai_lesson, skill=question.skill, position=9))
        )
        res = self.client.post(
            "/admin/assessment/questionversion/",
            {"action": "publish_selected", "_selected_action": [str(mine.pk), str(other.pk)]},
            follow=True,
        )
        self.assertContains(res, "Published 1 version(s).")
        self.assertContains(res, "Only the curriculum lead")  # AI Foundations isn't this lead's subject
        mine.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual((mine.status, other.status), ("published", "approved"))

    def test_status_cannot_be_typed_in_as_published(self):
        form_class = modelform_factory(ContentVersion, form=VersionStatusForm, fields=["status"])
        version = self.approved(self.maths8_lesson)
        form = form_class(data={"status": "published"}, instance=version, initial={"status": version.status})
        self.assertFalse(form.is_valid())
        self.assertIn("status", form.errors)
        form = form_class(data={"status": "in_review"}, instance=version, initial={"status": version.status})
        self.assertTrue(form.is_valid(), form.errors)

    def test_published_status_cannot_be_changed_back_in_the_form(self):
        form_class = modelform_factory(ContentVersion, form=VersionStatusForm, fields=["status"])
        version = services.publish(self.approved(self.maths8_lesson), self.lead("l@example.com", self.maths))
        form = form_class(data={"status": "draft"}, instance=version, initial={"status": version.status})
        self.assertFalse(form.is_valid())


class RoleAdminTests(TestCase):
    def request_as(self, user):
        request = RequestFactory().get("/admin/")
        request.user = user
        return request

    def test_only_super_admins_grant_roles(self):
        grant_admin = site._registry[RoleGrant]
        staff = make_user("staff@example.com", is_staff=True)
        staff.user_permissions.set(
            Permission.objects.filter(content_type__app_label="accounts", codename__endswith="rolegrant")
        )
        self.assertFalse(grant_admin.has_add_permission(self.request_as(staff)))
        self.assertFalse(grant_admin.has_change_permission(self.request_as(staff)))
        superuser = User.objects.create_superuser(email="su@example.com", password="x-long-pass-1", full_name="Super")
        self.assertTrue(grant_admin.has_add_permission(self.request_as(superuser)))
        self.assertFalse(grant_admin.has_delete_permission(self.request_as(superuser)))  # revoke, never delete

    def test_granting_a_role_is_recorded(self):
        superuser = User.objects.create_superuser(email="su@example.com", password="x-long-pass-1", full_name="Super")
        target = make_user("new-lead@example.com")
        self.client.force_login(superuser)
        res = self.client.post(
            "/admin/accounts/rolegrant/add/",
            {"user": str(target.pk), "role": "curriculum_lead", "subject": "", "class_level": ""},
        )
        self.assertEqual(res.status_code, 302, res.content[:2000])
        grant = RoleGrant.objects.get(user=target)
        self.assertEqual(grant.granted_by, superuser)
        self.assertTrue(AuditLog.objects.filter(action="role.granted", actor=superuser).exists())

    def test_staff_cannot_give_themselves_admin_access(self):
        user_admin = site._registry[User]
        staff = make_user("staff@example.com", is_staff=True)
        readonly = user_admin.get_readonly_fields(self.request_as(staff), staff)
        for field in ("is_staff", "is_superuser", "groups", "user_permissions"):
            self.assertIn(field, readonly)
        superuser = User.objects.create_superuser(email="su@example.com", password="x-long-pass-1", full_name="Super")
        self.assertNotIn("is_superuser", user_admin.get_readonly_fields(self.request_as(superuser), staff))
