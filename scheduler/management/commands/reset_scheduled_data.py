from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from planning.models import (
    AssignmentAttachment,
    AssignmentComment,
    AssignmentPlanItem,
    AssignmentSubmission,
    CourseAssignmentTemplate,
    StudentAssignment,
)
from scheduler.models import ScheduledLesson, Vacation


class Command(BaseCommand):
    help = (
        "Delete previously created scheduled data (assignments, lessons, vacations) "
        "to reset planning and scheduling state."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Required flag. Command will not run without explicit confirmation.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if not options.get("confirm"):
            raise CommandError("Refusing to run without --confirm.")

        deletion_plan = [
            ("assignment_submissions", AssignmentSubmission),
            ("assignment_comments", AssignmentComment),
            ("assignment_attachments", AssignmentAttachment),
            ("student_assignments", StudentAssignment),
            ("assignment_plan_items", AssignmentPlanItem),
            ("course_assignment_templates", CourseAssignmentTemplate),
            ("scheduled_lessons", ScheduledLesson),
            ("vacations", Vacation),
        ]

        self.stdout.write(self.style.WARNING("Resetting scheduled data..."))
        total_deleted = 0
        for label, model in deletion_plan:
            deleted, _ = model.objects.all().delete()
            total_deleted += deleted
            self.stdout.write(f"{label}: {deleted}")

        self.stdout.write(self.style.SUCCESS(f"Done. Total deleted rows: {total_deleted}"))
