"""Load the launch reference data (PRODUCT_DESIGN.md decision 4). Safe to run many times."""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalogue.models import Board, ClassLevel, Discipline, Subject

BOARDS = [
    ("CBSE", "Central Board of Secondary Education"),
    ("ICSE", "Council for the Indian School Certificate Examinations (ICSE/ISC)"),
    ("WBBSE", "West Bengal Board of Secondary Education"),
]
DISCIPLINES = [
    # (name, slug, order, [(subject name, slug, order), ...])
    ("Mathematics", "mathematics", 1, [("Mathematics", "mathematics", 1)]),
    (
        "Natural Sciences",
        "natural-sciences",
        2,
        [
            ("Science", "science", 1),  # Classes 6–10
            ("Physics", "physics", 2),  # Classes 11–12
            ("Chemistry", "chemistry", 3),
            ("Biology", "biology", 4),
        ],
    ),
    ("Computing & AI", "computing-ai", 3, [("AI Foundations", "ai-foundations", 1)]),
]


class Command(BaseCommand):
    help = "Create or update boards, classes 6–12, disciplines and launch subjects."

    @transaction.atomic
    def handle(self, *args, **options):
        for code, name in BOARDS:
            Board.objects.update_or_create(code=code, defaults={"name": name})
        for number in range(6, 13):
            ClassLevel.objects.update_or_create(number=number, defaults={"label": f"Class {number}"})
        for d_name, d_slug, d_order, subjects in DISCIPLINES:
            discipline, _ = Discipline.objects.update_or_create(
                slug=d_slug, defaults={"name": d_name, "order": d_order}
            )
            for s_name, s_slug, s_order in subjects:
                Subject.objects.update_or_create(
                    slug=s_slug, defaults={"name": s_name, "order": s_order, "discipline": discipline}
                )
        if options.get("verbosity", 1) > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Reference data ready: {Board.objects.count()} boards, {ClassLevel.objects.count()} classes, "
                    f"{Discipline.objects.count()} disciplines, {Subject.objects.count()} subjects."
                )
            )
