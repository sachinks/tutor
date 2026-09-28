"""Create the first superuser from environment variables, for hosts without a shell (Render free tier).

    DJANGO_SUPERUSER_EMAIL, DJANGO_SUPERUSER_PASSWORD   required; set only in the host's environment settings
    DJANGO_SUPERUSER_NAME                               optional display name (default "Administrator")

Safe to run on every deploy: with the variables unset it does nothing, and an existing account with that email is
never changed (its password is not reset and it is not promoted). The password must pass the normal password rules.
"""

import os

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import User
from apps.operations import audit


class Command(BaseCommand):
    help = "Create a superuser from DJANGO_SUPERUSER_EMAIL / DJANGO_SUPERUSER_PASSWORD if it doesn't exist yet."

    @transaction.atomic
    def handle(self, *args, **options):
        email = (os.environ.get("DJANGO_SUPERUSER_EMAIL") or "").strip().lower()
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD") or ""
        name = (os.environ.get("DJANGO_SUPERUSER_NAME") or "Administrator").strip()
        if not email or not password:
            self.stdout.write("ensure_superuser: DJANGO_SUPERUSER_EMAIL/PASSWORD not set; skipped.")
            return

        existing = User.objects.filter(email__iexact=email).first()
        if existing:
            state = "is a superuser" if existing.is_superuser else "exists but is NOT a superuser (left unchanged)"
            self.stdout.write(f"ensure_superuser: {email} {state}.")
            return

        candidate = User(email=email, full_name=name)
        try:
            validate_password(password, candidate)
        except ValidationError as exc:
            raise CommandError("DJANGO_SUPERUSER_PASSWORD is too weak: " + " ".join(exc.messages)) from None

        user = User.objects.create_superuser(email=email, password=password, full_name=name)
        audit.record(None, "user.superuser_created", user, after={"source": "ensure_superuser"})
        self.stdout.write(self.style.SUCCESS(f"ensure_superuser: created superuser {email}."))
