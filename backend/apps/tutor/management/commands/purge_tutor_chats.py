"""Delete tutor chats past their retention period (decision D40).

    python manage.py purge_tutor_chats            # delete
    python manage.py purge_tutor_chats --dry-run  # only count

A chat is deleted TUTOR_CHAT_RETENTION_DAYS (90) after its last message, unless it has a safety flag that is still
open or reviewed, or one closed less than the retention period ago. build.sh runs it on every deploy; production
also runs it daily (cron), because deploys are not daily.
"""

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from apps.tutor.models import SafetyFlag, TutorConversation


class Command(BaseCommand):
    help = "Delete tutor chats older than the retention period (D40)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Count what would be deleted; delete nothing.")

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=settings.TUTOR_CHAT_RETENTION_DAYS)
        keep_for_flags = SafetyFlag.objects.filter(
            Q(status__in=[SafetyFlag.Status.OPEN, SafetyFlag.Status.REVIEWED]) | Q(closed_at__gte=cutoff)
        ).values("conversation_id")
        expired = TutorConversation.objects.filter(last_message_at__lt=cutoff).exclude(pk__in=keep_for_flags)
        count = expired.count()
        if options["dry_run"]:
            self.stdout.write(f"{count} tutor chat(s) would be deleted (last message before {cutoff:%Y-%m-%d}).")
            return
        expired.delete()
        self.stdout.write(f"Deleted {count} tutor chat(s) with no message since {cutoff:%Y-%m-%d}.")
