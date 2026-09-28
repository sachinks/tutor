from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    """Creates users who log in with an email or a mobile number (DATA_MODEL.md M2)."""

    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        email = self.normalize_email(email).lower() if email else None
        mobile = extra_fields.get("mobile") or None
        extra_fields["mobile"] = mobile
        if not email and not mobile:
            raise ValueError("A user needs an email or a mobile number.")
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email=None, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("account_type", "staff")
        if extra_fields.get("is_staff") is not True or extra_fields.get("is_superuser") is not True:
            raise ValueError("A superuser must have is_staff=True and is_superuser=True.")
        return self._create_user(email, password, **extra_fields)
