"""Bring the AI service's lesson index in step with published content.

    python manage.py sync_ai_index            # reconcile, then send every due request
    python manage.py sync_ai_index --all      # also retry requests still waiting for their backoff
    python manage.py sync_ai_index --strict   # exit with an error if the AI service can't be reached

build.sh runs it on every deploy (Render's free tier has no worker or cron), so a missed update is repaired at the
next deploy at the latest. Without --strict an unreachable AI service is a warning, never a failed deploy.
"""

from django.core.management.base import BaseCommand, CommandError

from apps.aiservice import indexing
from apps.aiservice.client import AIServiceError, get_client, is_configured
from apps.aiservice.models import IndexRequest


class Command(BaseCommand):
    help = "Reconcile the AI lesson index with published content and send pending index requests."

    def add_arguments(self, parser):
        parser.add_argument("--no-reconcile", action="store_true", help="Only send requests already queued.")
        parser.add_argument("--all", action="store_true", help="Also send requests waiting for their retry time.")
        parser.add_argument("--limit", type=int, default=500, help="At most this many requests (default 500).")
        parser.add_argument("--strict", action="store_true", help="Fail if the AI service is missing or down.")

    def handle(self, *args, **options):
        if options["limit"] < 1:
            raise CommandError("--limit must be at least 1.")
        if not is_configured():
            waiting = IndexRequest.objects.filter(status=IndexRequest.Status.PENDING).count()
            message = f"No AI service configured (TUTOR_AI_URL, TUTOR_AI_SERVICE_TOKEN); {waiting} request(s) queued."
            if options["strict"]:
                raise CommandError(message)
            self.stdout.write(message)
            return

        try:
            with get_client() as client:
                if not options["no_reconcile"]:
                    summary = indexing.reconcile(client)
                    self.stdout.write(
                        "Reconciled: {published} published, {indexed} indexed, {queued} queued, "
                        "{already_queued} already queued, {skipped} skipped (refused earlier).".format(**summary)
                    )
                outcomes = indexing.process(client, limit=options["limit"], include_waiting=options["all"])
        except AIServiceError as exc:
            message = f"AI service unavailable: {exc}"
            if options["strict"]:
                raise CommandError(message) from exc
            self.stderr.write(self.style.WARNING(message))
            return

        counts = ", ".join(f"{outcomes[k]} {k}" for k in ("done", "retry", "failed", "requeued") if outcomes[k])
        self.stdout.write(f"Sent: {counts or 'nothing due'}.")
        if outcomes["stopped"]:
            self.stderr.write(self.style.WARNING("Stopped early: the AI service stopped answering."))
            if options["strict"]:
                raise CommandError("The AI service stopped answering.")
        if outcomes["failed"]:
            self.stderr.write(self.style.WARNING("Some requests failed for good; see AI service → Index requests."))
