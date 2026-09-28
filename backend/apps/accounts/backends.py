from django.contrib.auth.backends import ModelBackend
from django.db.models import Q

from .models import User


class EmailOrMobileBackend(ModelBackend):
    """Log in with an email address or a mobile number (DATA_MODEL.md M2)."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        identifier = (username or kwargs.get("email") or kwargs.get("mobile") or "").strip()
        if not identifier or password is None:
            return None
        lookup = Q(email__iexact=identifier) if "@" in identifier else Q(mobile=identifier)
        try:
            user = User.objects.get(lookup)
        except User.DoesNotExist:
            User().set_password(password)  # same work as a real check, so timing reveals nothing
            return None
        if user.deleted_at is None and user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
