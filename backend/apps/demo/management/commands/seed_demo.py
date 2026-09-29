"""Load the demo world: courses, programmes, people, learning history and content under review.

    python manage.py seed_demo                  # create or refresh everything (idempotent)
    python manage.py seed_demo --reset-activity # also rebuild the students' learning history (fresh streaks)

Allowed only where TUTOR_DEMO_DATA=true (local development and the hosted demo; never production). People are
created only when TUTOR_DEMO_PASSWORD is set; they all share that password. See docs/testing/demo-data.md.
"""

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from apps.demo import activity, content, people, workflow


def build_demo(password, reset_activity=False, stdout=None):
    """Shared by seed_demo and the local-only seed_test_accounts. Returns a summary dict."""
    call_command("seed_reference", verbosity=0)
    call_command("seed_consent", verbosity=0)
    call_command("seed_demo_catalogue", verbosity=0)
    summary = {"content": content.load()}
    if password:
        summary["people"] = people.build(password)
        summary["workflow_versions"] = workflow.build()
        if reset_activity:
            activity.reset()
        summary["quizzes"] = activity.build()
    return summary


class Command(BaseCommand):
    help = "Create or refresh demo courses, people and learning history (only where TUTOR_DEMO_DATA=true)."

    def add_arguments(self, parser):
        parser.add_argument("--reset-activity", action="store_true", help="Rebuild demo students' learning history.")

    def handle(self, *args, **options):
        if not getattr(settings, "TUTOR_DEMO_DATA", False):
            raise CommandError("Refusing: TUTOR_DEMO_DATA is not true. Demo data never goes into production.")
        password = settings.TUTOR_DEMO_PASSWORD
        if password:
            try:
                validate_password(password)
            except ValidationError as exc:
                raise CommandError("TUTOR_DEMO_PASSWORD is too weak: " + " ".join(exc.messages)) from None
        summary = build_demo(password, reset_activity=options["reset_activity"])
        report = summary["content"]
        self.stdout.write(
            f"seed_demo: {report.courses} courses, {report.lessons} lessons, {report.questions} new questions, "
            f"{report.programmes} programmes."
        )
        if not password:
            self.stdout.write(self.style.WARNING("seed_demo: TUTOR_DEMO_PASSWORD not set; demo people skipped."))
            return
        self.stdout.write(
            self.style.SUCCESS(
                f"seed_demo: {summary['people'].users} people, {summary['workflow_versions']} versions under review, "
                f"{summary['quizzes']} quizzes of history. Accounts: docs/testing/demo-data.md"
            )
        )
