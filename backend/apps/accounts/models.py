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
    mobile = models.CharField(
        max_length=16, unique=True, null=True, blank=True, validators=[mobile_validator]
    )
    email_verified_at = models.DateTimeField(null=True, blank=True)
    mobile_verified_at = models.DateTimeField(null=True, blank=True)
    account_type = models.CharField(
        max_length=10, choices=AccountType.choices, default=AccountType.STUDENT
    )
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
