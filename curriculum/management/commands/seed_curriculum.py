"""Management command to seed the database with Oak National Academy curriculum lessons.

Usage:
    python manage.py seed_curriculum --file docs/seed_sample.csv

The command reads a CSV file where each row represents a single Oak lesson.
Required CSV columns:
    key_stage, subject_name, programme_slug, year, unit_slug, unit_title,
    lesson_number, lesson_title, lesson_url

The command is idempotent: running it twice with the same file will not create
duplicate records. It uses ``Lesson.objects.get_or_create(lesson_url=...)`` so
each unique lesson URL is the deduplication key.

Expected full dataset: ~10,055 rows from the Oak National Academy export.
"""

import csv
import os

from django.core.management.base import BaseCommand, CommandError

from curriculum.models import Lesson

PROGRESS_EVERY = 500


class Command(BaseCommand):
    """Load Oak National Academy lesson data from a CSV file into the database."""

    help = 'Seed the curriculum_lesson table from an Oak National Academy CSV export.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            required=True,
            metavar='CSV_PATH',
            help='Path to the Oak National Academy lessons CSV file.',
        )

    def handle(self, *args, **options):
        csv_path = options['file']

        if not os.path.isfile(csv_path):
            raise CommandError(f'File not found: {csv_path}')

        created_count = 0
        existing_count = 0
        row_number = 0

        self.stdout.write(f'Reading {csv_path} …')

        with open(csv_path, newline='', encoding='utf-8') as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                row_number += 1
                _, created = Lesson.objects.get_or_create(
                    lesson_url=row['lesson_url'],
                    defaults={
                        'key_stage': row['key_stage'],
                        'subject_name': row['subject_name'],
                        'programme_slug': row['programme_slug'],
                        'year': row['year'],
                        'unit_slug': row['unit_slug'],
                        'unit_title': row['unit_title'],
                        'lesson_number': int(row['lesson_number']),
                        'lesson_title': row['lesson_title'],
                    },
                )
                if created:
                    created_count += 1
                else:
                    existing_count += 1

                if row_number % PROGRESS_EVERY == 0:
                    self.stdout.write(f'  … processed {row_number} rows')

        total = created_count + existing_count
        self.stdout.write(
            self.style.SUCCESS(
                f'Seeded: {created_count} created, {existing_count} already existed. '
                f'Total: {total} lessons.'
            )
        )
