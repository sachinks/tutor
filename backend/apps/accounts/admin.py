from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import ReadOnlyPasswordHashField

from .models import User


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
        fields = "__all__"


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
        (None, {"classes": ("wide",), "fields": ("full_name", "email", "mobile", "account_type", "password1", "password2")}),
    )
    filter_horizontal = ("groups", "user_permissions")
