import uuid

from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import PermissionsMixin
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from .managers import UserManager

mobile_validator = RegexValidator(
    regex=r"^\+[1-9]\d{7,14}$",
    message="Mobile must be in international format, e.g. +919876543210.",
)


class User(AbstractBaseUser, PermissionsMixin):
    """One login for everyone: student, parent, teacher, staff (DATA_MODEL.md §4, M1–M3).

    Permissions for teaching and admin work come from role grants (added in step 5),
    not from account_type, which only records how the person signed up.
    """

    class AccountType(models.TextChoices):
        STUDENT = "student", "Student"
        PARENT = "parent", "Parent"
        TEACHER = "teacher", "Teacher"
        STAFF = "staff", "Staff"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    full_name = models.CharField(max_length=150)
    email = models.EmailField(unique=True, null=True, blank=True)
    mobile = models.CharField(max_length=16, unique=True, null=True, blank=True, validators=[mobile_validator])
    email_verified_at = models.DateTimeField(null=True, blank=True)
    mobile_verified_at = models.DateTimeField(null=True, blank=True)
    account_type = models.CharField(max_length=10, choices=AccountType.choices, default=AccountType.STUDENT)
    is_active = models.BooleanField(default=True, help_text="Untick to suspend the account.")
    is_staff = models.BooleanField(default=False, help_text="Can log in to the Django admin.")
    date_joined = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(email__isnull=False) | Q(mobile__isnull=False),
                name="user_has_email_or_mobile",
            )
        ]

    def save(self, *args, **kwargs):
        # Empty strings become NULL so the unique constraints ignore them.
        self.email = self.email.strip().lower() if self.email else None
        self.mobile = self.mobile.strip() if self.mobile else None
        super().save(*args, **kwargs)

    def get_full_name(self):
        return self.full_name

    def get_short_name(self):
        return self.full_name.split(" ")[0] if self.full_name else ""

    def __str__(self):
        return f"{self.full_name} <{self.email or self.mobile}>"


# ---------------------------------------------------------------------------
# Profiles (one per kind of person; one User may have several, decision A2)
# ---------------------------------------------------------------------------


class StudentProfile(models.Model):
    class Status(models.TextChoices):
        AWAITING_CONSENT = "awaiting_consent", "Awaiting parent approval"
        ACTIVE = "active", "Active"
        PAUSED = "paused", "Paused (consent withdrawn)"
        DELETED = "deleted", "Deleted"

    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True, related_name="student_profile")
    class_level = models.ForeignKey("catalogue.ClassLevel", on_delete=models.PROTECT)
    board = models.ForeignKey("catalogue.Board", on_delete=models.PROTECT)
    city = models.CharField(max_length=80)
    school_name = models.CharField(max_length=150, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.AWAITING_CONSENT)
    awaiting_since = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.full_name} ({self.class_level}, {self.board})"


class ParentProfile(models.Model):
    class NotifyBy(models.TextChoices):
        SMS = "sms", "SMS"
        EMAIL = "email", "Email"
        BOTH = "both", "SMS and email"

    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True, related_name="parent_profile")
    preferred_language = models.CharField(max_length=10, default="en")
    notify_by = models.CharField(max_length=5, choices=NotifyBy.choices, default=NotifyBy.BOTH)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.user.full_name


class TeacherProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True, related_name="teacher_profile")
    display_name = models.CharField(max_length=150)
    short_bio = models.TextField(blank=True)
    qualifications = models.TextField(blank=True)
    experience = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.display_name


# ---------------------------------------------------------------------------
# Parent ↔ child and consent
# ---------------------------------------------------------------------------


class GuardianLink(models.Model):
    class Relationship(models.TextChoices):
        MOTHER = "mother", "Mother"
        FATHER = "father", "Father"
        GUARDIAN = "guardian", "Guardian"
        OTHER = "other", "Other"

    parent = models.ForeignKey(User, on_delete=models.CASCADE, related_name="children_links")
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="guardian_links")
    relationship = models.CharField(max_length=10, choices=Relationship.choices, default=Relationship.GUARDIAN)
    is_primary = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            # v1: exactly one active primary guardian per student (decision Q9)
            models.UniqueConstraint(
                fields=["student"],
                condition=Q(is_primary=True, ended_at__isnull=True),
                name="one_active_primary_guardian",
            ),
            models.UniqueConstraint(
                fields=["parent", "student"],
                condition=Q(ended_at__isnull=True),
                name="one_active_link_per_pair",
            ),
        ]

    def __str__(self):
        return f"{self.parent.full_name} → {self.student.full_name}"


class ConsentText(models.Model):
    """Exactly what a parent read when consenting. Never edited; add a new version instead."""

    version = models.CharField(max_length=30, primary_key=True)  # e.g. "2026-10-v1"
    body = models.TextField()
    effective_from = models.DateField()

    class Meta:
        ordering = ["-effective_from"]

    def __str__(self):
        return self.version

    @classmethod
    def current(cls):
        return cls.objects.filter(effective_from__lte=timezone.localdate()).first()


class ConsentRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    guardian_link = models.ForeignKey(GuardianLink, on_delete=models.CASCADE, related_name="consents")
    consent_text = models.ForeignKey(ConsentText, on_delete=models.PROTECT)
    given_at = models.DateTimeField(default=timezone.now)
    given_ip = models.GenericIPAddressField(null=True, blank=True)  # evidence of consent (decision A1)
    withdrawn_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-given_at"]

    def __str__(self):
        state = "active" if self.is_active else "withdrawn"
        return f"Consent {self.consent_text_id} for {self.guardian_link} ({state})"

    @property
    def is_active(self):
        return self.withdrawn_at is None


class ApprovalRequest(models.Model):
    """The link sent to a parent when a student signs up (journey S4–S5, P1)."""

    class Channel(models.TextChoices):
        SMS = "sms", "SMS"
        EMAIL = "email", "Email"

    class Status(models.TextChoices):
        SENT = "sent", "Sent"
        APPROVED = "approved", "Approved"
        DECLINED = "declined", "Declined"
        EXPIRED = "expired", "Expired"
        REPORTED = "reported", "Reported (not my child)"

    VALID_DAYS = 7
    MAX_SENDS_PER_DAY = 3

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="approval_requests")
    parent_contact = models.CharField(max_length=254)
    channel = models.CharField(max_length=5, choices=Channel.choices)
    token_hash = models.CharField(max_length=64, unique=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SENT)
    send_count = models.PositiveSmallIntegerField(default=1)
    last_sent_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="approvals_given"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Approval for {self.student.full_name} via {self.channel} ({self.status})"

    @property
    def is_usable(self):
        return self.status == self.Status.SENT and self.expires_at > timezone.now()


class VerificationCode(models.Model):
    """One-time codes sent by SMS/email. Only the hash is stored."""

    class Purpose(models.TextChoices):
        VERIFY_CONTACT = "verify_contact", "Verify contact"
        LOGIN = "login", "Log in"
        RESET_PASSWORD = "reset_password", "Reset password"

    VALID_MINUTES = 10
    MAX_ATTEMPTS = 5

    destination = models.CharField(max_length=254)
    purpose = models.CharField(max_length=20, choices=Purpose.choices)
    code_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["destination", "purpose", "created_at"])]

    def __str__(self):
        return f"{self.purpose} code for {self.destination}"


# ---------------------------------------------------------------------------
# Roles (scoped to subject + class for teacher roles)
# ---------------------------------------------------------------------------


class RoleGrant(models.Model):
    class Role(models.TextChoices):
        AUTHOR = "author", "Author"
        REVIEWER = "reviewer", "Reviewer"
        BATCH_TEACHER = "batch_teacher", "Batch teacher"
        CURRICULUM_LEAD = "curriculum_lead", "Curriculum lead"
        OPERATIONS = "operations", "Operations"
        SUPER_ADMIN = "super_admin", "Super admin"

    TEACHER_ROLES = {Role.AUTHOR, Role.REVIEWER, Role.BATCH_TEACHER}

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="role_grants")
    role = models.CharField(max_length=20, choices=Role.choices)
    subject = models.ForeignKey("catalogue.Subject", on_delete=models.PROTECT, null=True, blank=True)
    class_level = models.ForeignKey("catalogue.ClassLevel", on_delete=models.PROTECT, null=True, blank=True)
    granted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="roles_granted")
    granted_at = models.DateTimeField(default=timezone.now)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "role", "subject", "class_level"],
                condition=Q(revoked_at__isnull=True),
                name="one_active_grant_per_scope",
                nulls_distinct=False,
            )
        ]

    def __str__(self):
        scope = " / ".join(str(x) for x in (self.subject, self.class_level) if x) or "all"
        return f"{self.user.full_name}: {self.get_role_display()} ({scope})"


def has_role(user, role, subject=None, class_level=None):
    """True if the user holds an active grant for this role and scope."""
    grants = RoleGrant.objects.filter(user=user, role=role, revoked_at__isnull=True)
    if subject is not None:
        grants = grants.filter(Q(subject=subject) | Q(subject__isnull=True))
    if class_level is not None:
        grants = grants.filter(Q(class_level=class_level) | Q(class_level__isnull=True))
    return grants.exists()
