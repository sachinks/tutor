from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from django.contrib.auth.password_validation import validate_password

from apps.operations import audit

from . import permissions
from .models import (
    ApprovalRequest,
    ConsentRecord,
    ConsentText,
    GuardianLink,
    ParentProfile,
    RoleGrant,
    StudentProfile,
    TeacherProfile,
    User,
    VerificationCode,
)


class UserCreationForm(forms.ModelForm):
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirm password", widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ("full_name", "email", "mobile", "account_type")

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("email") and not cleaned.get("mobile"):
            raise forms.ValidationError("Enter an email or a mobile number.")
        if cleaned.get("password1") != cleaned.get("password2"):
            self.add_error("password2", "Passwords don't match.")
        elif cleaned.get("password1"):
            candidate = User(full_name=cleaned.get("full_name", ""), email=cleaned.get("email"))
            try:
                validate_password(cleaned["password1"], candidate)  # same rules as sign-up
            except forms.ValidationError as exc:
                self.add_error("password1", exc)
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class UserChangeForm(forms.ModelForm):
    password = ReadOnlyPasswordHashField()

    class Meta:
        model = User
        fields = (
            "full_name",
            "email",
            "mobile",
            "email_verified_at",
            "mobile_verified_at",
            "account_type",
            "is_active",
            "deleted_at",
            "is_staff",
            "is_superuser",
            "groups",
            "user_permissions",
        )


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    list_display = ("full_name", "email", "mobile", "account_type", "is_active", "is_staff", "date_joined")
    list_filter = ("account_type", "is_active", "is_staff")
    search_fields = ("full_name", "email", "mobile")
    ordering = ("-date_joined",)
    readonly_fields = ("id", "date_joined", "updated_at", "last_login")
    fieldsets = (
        (None, {"fields": ("id", "full_name", "email", "mobile", "password")}),
        ("Verification", {"fields": ("email_verified_at", "mobile_verified_at")}),
        ("Account", {"fields": ("account_type", "is_active", "deleted_at")}),
        ("Admin access", {"fields": ("is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Dates", {"fields": ("date_joined", "updated_at", "last_login")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("full_name", "email", "mobile", "account_type", "password1", "password2"),
            },
        ),
    )
    filter_horizontal = ("groups", "user_permissions")

    ADMIN_ACCESS_FIELDS = ("is_staff", "is_superuser", "groups", "user_permissions")

    def get_readonly_fields(self, request, obj=None):
        """Only a super admin can hand out admin access; otherwise any staff member could promote themselves."""
        fields = list(super().get_readonly_fields(request, obj))
        if not permissions.is_super_admin(request.user):
            fields += [f for f in self.ADMIN_ACCESS_FIELDS if f not in fields]
        return fields


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "class_level", "board", "city", "status", "awaiting_since")
    list_filter = ("status", "class_level", "board")
    search_fields = ("user__full_name", "user__email", "user__mobile", "city")
    raw_id_fields = ("user",)


@admin.register(ParentProfile)
class ParentProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "preferred_language", "notify_by")
    search_fields = ("user__full_name", "user__email", "user__mobile")
    raw_id_fields = ("user",)


@admin.register(TeacherProfile)
class TeacherProfileAdmin(admin.ModelAdmin):
    list_display = ("display_name", "user")
    search_fields = ("display_name", "user__email", "user__mobile")
    raw_id_fields = ("user",)


class ConsentRecordInline(admin.TabularInline):
    model = ConsentRecord
    extra = 0
    readonly_fields = ("consent_text", "given_at", "given_ip", "withdrawn_at")
    can_delete = False


@admin.register(GuardianLink)
class GuardianLinkAdmin(admin.ModelAdmin):
    list_display = ("parent", "student", "relationship", "is_primary", "created_at", "ended_at")
    list_filter = ("relationship", "is_primary")
    search_fields = ("parent__full_name", "student__full_name")
    raw_id_fields = ("parent", "student")
    inlines = [ConsentRecordInline]


@admin.register(ConsentText)
class ConsentTextAdmin(admin.ModelAdmin):
    list_display = ("version", "effective_from")

    def get_readonly_fields(self, request, obj=None):
        # A published consent text is never edited: add a new version instead.
        return ("version", "body", "effective_from") if obj else ()


@admin.register(ApprovalRequest)
class ApprovalRequestAdmin(admin.ModelAdmin):
    list_display = ("student", "channel", "status", "send_count", "expires_at", "created_at")
    list_filter = ("status", "channel")
    search_fields = ("student__full_name",)
    readonly_fields = ("token_hash",)
    raw_id_fields = ("student", "approved_by")


@admin.register(VerificationCode)
class VerificationCodeAdmin(admin.ModelAdmin):
    list_display = ("destination", "purpose", "expires_at", "attempts", "used_at")
    list_filter = ("purpose",)
    readonly_fields = ("code_hash",)


@admin.register(RoleGrant)
class RoleGrantAdmin(admin.ModelAdmin):
    """Roles are revoked (revoked_at), never deleted, so the history of who could do what is kept."""

    list_display = ("user", "role", "subject", "class_level", "granted_by", "granted_at", "revoked_at")
    list_filter = ("role", "subject", "class_level")
    search_fields = ("user__full_name", "user__email")
    raw_id_fields = ("user",)
    readonly_fields = ("granted_by", "granted_at")

    def has_add_permission(self, request):
        return permissions.can_manage_roles(request.user)

    def has_change_permission(self, request, obj=None):
        return permissions.can_manage_roles(request.user)

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        if not change:
            obj.granted_by = request.user
        super().save_model(request, obj, form, change)
        action = "role.revoked" if obj.revoked_at else ("role.changed" if change else "role.granted")
        audit.record(request.user, action, obj, after={"role": obj.role, "user": str(obj.user_id)})
