"""Write the API's OpenAPI schema to docs/architecture/openapi.json (quality backlog Q12).

The committed file is the API contract. `./dev.sh` regenerates it, so every pull request that changes the API also
changes this file and reviewers see exactly what changed. CI runs `--check`, which fails if the committed contract
is out of date, so an API change can't slip in unreviewed.

    python manage.py export_openapi           # write
    python manage.py export_openapi --check   # exit 1 if the file differs from the code
"""

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

DEFAULT_PATH = Path(settings.BASE_DIR).parent / "docs" / "architecture" / "openapi.json"


def render_schema() -> str:
    """The contract, without local-only tester tools (they exist only with DEBUG + TUTOR_DEV_TOOLS)."""
    from config.api import api

    schema = api.get_openapi_schema()
    schema["paths"] = {p: ops for p, ops in schema["paths"].items() if not p.startswith("/api/v1/dev/")}
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


class Command(BaseCommand):
    help = "Export the OpenAPI schema (the API contract) to docs/architecture/openapi.json."

    def add_arguments(self, parser):
        parser.add_argument("--check", action="store_true", help="fail if the committed file is out of date")
        parser.add_argument("--path", type=Path, default=DEFAULT_PATH)

    def handle(self, *args, **options):
        path, current = options["path"], render_schema()
        if options["check"]:
            if not path.exists() or path.read_text(encoding="utf-8") != current:
                raise CommandError(
                    f"{path.name} is out of date: the API changed. Run `python manage.py export_openapi`, "
                    "review the diff and commit it."
                )
            self.stdout.write("OpenAPI contract is up to date.")
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(current, encoding="utf-8")
        self.stdout.write(f"Wrote {path}")
