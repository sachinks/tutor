"""Local shortcut for testers: the full demo world with the local password. Refuses unless DEBUG and
TUTOR_DEV_TOOLS are on. Equivalent to seed_demo with TUTOR_DEMO_PASSWORD=Test-Pass-2026 (docs/testing/demo-data.md).
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.demo.management.commands.seed_demo import build_demo
from apps.demo.people import PEOPLE

PASSWORD = "Test-Pass-2026"
# (key, name, mobile, email, kind), kept for the tester guide and older tests.
ACCOUNTS = [(p.key, p.name, p.mobile, p.email, p.kind) for p in PEOPLE]


class Command(BaseCommand):
    help = "Create or reset the demo accounts and data with the local tester password (local development only)."

    def add_arguments(self, parser):
        parser.add_argument("--reset-activity", action="store_true")

    def handle(self, *args, **options):
        if not (settings.DEBUG and getattr(settings, "TUTOR_DEV_TOOLS", False)):
            raise CommandError("Refusing: needs DJANGO_DEBUG=true and TUTOR_DEV_TOOLS=true (local development only).")
        build_demo(PASSWORD, reset_activity=options.get("reset_activity", False))
        if options.get("verbosity", 1) > 0:
            self.stdout.write(self.style.SUCCESS(f"Demo accounts ready (password for all: {PASSWORD}):"))
            for p in PEOPLE:
                self.stdout.write(f"  {p.key:<17} {p.name:<15} {p.mobile}  {p.email}  {p.story}")
