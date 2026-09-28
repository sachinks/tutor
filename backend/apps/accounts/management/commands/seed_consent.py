"""Create the first consent text. The wording is a DRAFT until reviewed by the privacy/legal owner."""

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import ConsentText

VERSION = "2026-10-draft-v1"
BODY = """DRAFT — to be reviewed by the privacy/legal owner before launch.

I am the parent or legal guardian of this child and I agree that TUTOR may:
1. Keep my child's name, class, board and city to run their account.
2. Record my child's lesson progress, quiz answers and batch attendance to measure what they have learned.
3. Let my child use the AI tutor. Conversations are stored so they can be reviewed for safety; I will see a topic summary and any safety-flagged conversation.
4. Contact me about my child's learning, payments and account.

TUTOR will not show ads to my child, sell my child's data, or make anything about my child public.
I can withdraw this consent at any time. My child's account is then paused, and their personal data is deleted after 30 days unless I restore consent."""


class Command(BaseCommand):
    help = "Create the first (draft) consent text if none exists."

    def handle(self, *args, **options):
        text, created = ConsentText.objects.get_or_create(
            version=VERSION, defaults={"body": BODY, "effective_from": timezone.localdate()}
        )
        if options.get("verbosity", 1) > 0:
            self.stdout.write(
                self.style.SUCCESS(f"Consent text {text.version} {'created' if created else 'already exists'}.")
            )
