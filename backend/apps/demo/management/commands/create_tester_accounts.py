"""Create personal tester accounts (one clean student each) and print their passwords ONCE.

    python manage.py create_tester_accounts --count 5 --confirm-host <database host>
    python manage.py create_tester_accounts --count 5 --confirm-host <host> --reset-passwords   # new passwords

To create them on the hosted demo from WSL, point DATABASE_URL at Neon for this one command (direct connection):

    DATABASE_URL='postgresql://…neon.tech/tutor?sslmode=require' \\
        python manage.py create_tester_accounts --count 5 --confirm-host ep-xxxx.c-4.ap-southeast-1.aws.neon.tech

Guards: only where TUTOR_DEMO_DATA=true, and --confirm-host must equal the database host this command will write to,
so it can never run against the wrong database by accident. Passwords are never logged or saved to a file; copy them
from the terminal into your password manager and hand one to each tester privately.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from apps.demo.testers import MAX_TESTERS, ensure_testers


class Command(BaseCommand):
    help = "Create personal tester accounts (clean students enrolled in every course) and print passwords once."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=5, help=f"how many testers (1–{MAX_TESTERS})")
        parser.add_argument("--confirm-host", required=True, help="the database host, typed out to confirm the target")
        parser.add_argument("--reset-passwords", action="store_true", help="give existing testers new passwords")

    def handle(self, *args, **options):
        if not getattr(settings, "TUTOR_DEMO_DATA", False):
            raise CommandError("Refusing: TUTOR_DEMO_DATA is not true. Tester accounts never go into production.")
        host = connection.settings_dict.get("HOST") or "localhost"
        if options["confirm_host"] != host:
            raise CommandError(f"Refusing: --confirm-host doesn't match the database this would write to ({host}).")
        try:
            results = ensure_testers(options["count"], reset_passwords=options["reset_passwords"])
        except ValueError as exc:
            raise CommandError(str(exc)) from None
        self.stdout.write(f"Database: {host}\n")
        self.stdout.write(f"{'Login (email)':<26} {'Mobile':<15} Password")
        for r in results:
            shown = r.password or "(unchanged; use --reset-passwords for a new one)"
            self.stdout.write(f"{r.email:<26} {r.mobile:<15} {shown}")
        self.stdout.write(
            self.style.WARNING(
                "\nPasswords are shown only now. Store them in a password manager; never commit or paste them in chat."
            )
        )
