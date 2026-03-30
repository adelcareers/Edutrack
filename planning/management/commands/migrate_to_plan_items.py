from collections import Counter

from django.core.management.base import BaseCommand

from courses.models import CourseSubjectConfig
from planning.models import ActivityProgress, AssignmentPlanItem, PlanItem, StudentAssignment
from planning.services import create_plan_item


class Command(BaseCommand):
    help = "Backfill PlanItem rows and bridge links from legacy planning data."
    DRY_RUN_SENTINEL = object()

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", dest="dry_run")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        counters = Counter()

        legacy_items = list(
            AssignmentPlanItem.objects.select_related(
                "course",
                "template",
                "template__assignment_type",
                "lesson_enrolled_subject",
                "scheduled_lesson__lesson",
                "scheduled_lesson__enrolled_subject",
                "scheduled_lesson__course_subject",
            ).order_by("course_id", "week_number", "day_number", "order", "id")
        )

        for legacy_item in legacy_items:
            counters["scanned_legacy_rows"] += 1
            canonical = self._find_canonical_plan_item(legacy_item, counters)

            if canonical is None:
                canonical, created_config = self._build_plan_item_from_legacy(
                    legacy_item, dry_run=dry_run
                )
                counters["created_course_subject_configs"] += int(created_config)
                if canonical is not None:
                    counters["created_plan_items"] += 1
            if canonical is None:
                counters["skipped_conflicts"] += 1
                continue

            counters["repaired_scheduled_lessons"] += self._repair_scheduled_lesson(
                legacy_item, canonical, dry_run=dry_run
            )
            counters["repaired_student_assignments"] += self._repair_assignments(
                legacy_item, canonical, dry_run=dry_run
            )
            counters["repaired_activity_progress"] += self._repair_activities(
                legacy_item, canonical, dry_run=dry_run
            )

        for key in (
            "scanned_legacy_rows",
            "created_course_subject_configs",
            "created_plan_items",
            "repaired_scheduled_lessons",
            "repaired_student_assignments",
            "repaired_activity_progress",
            "skipped_conflicts",
        ):
            self.stdout.write(f"{key}={counters[key]}")

    def _find_canonical_plan_item(self, legacy_item, counters):
        linked_ids = set()
        if legacy_item.scheduled_lesson_id and legacy_item.scheduled_lesson.plan_item_id:
            linked_ids.add(legacy_item.scheduled_lesson.plan_item_id)
        linked_ids.update(
            StudentAssignment.objects.filter(plan_item=legacy_item)
            .exclude(new_plan_item_id__isnull=True)
            .values_list("new_plan_item_id", flat=True)
        )
        linked_ids.update(
            ActivityProgress.objects.filter(plan_item=legacy_item)
            .exclude(new_plan_item_id__isnull=True)
            .values_list("new_plan_item_id", flat=True)
        )
        linked_ids.discard(None)

        if len(linked_ids) > 1:
            counters["skipped_conflicts"] += 1
            return None
        if linked_ids:
            return PlanItem.objects.filter(pk=next(iter(linked_ids))).first()

        item_type = {
            "lesson": PlanItem.ITEM_TYPE_LESSON,
            "activity": PlanItem.ITEM_TYPE_ACTIVITY,
            "assignment": PlanItem.ITEM_TYPE_ASSIGNMENT,
        }.get(legacy_item.template.item_kind, PlanItem.ITEM_TYPE_ASSIGNMENT)
        return PlanItem.objects.filter(
            course=legacy_item.course,
            item_type=item_type,
            week_number=legacy_item.week_number,
            day_number=legacy_item.day_number,
            order=legacy_item.order,
            name=legacy_item.template.name,
        ).first()

    def _infer_course_subject_config(self, legacy_item, dry_run=False):
        scheduled_lesson = legacy_item.scheduled_lesson
        if scheduled_lesson and scheduled_lesson.course_subject_id:
            return scheduled_lesson.course_subject, False

        enrolled_subject = legacy_item.lesson_enrolled_subject
        if enrolled_subject is None and scheduled_lesson is not None:
            enrolled_subject = scheduled_lesson.enrolled_subject
        if enrolled_subject is None:
            return None, False

        defaults = {
            "key_stage": enrolled_subject.key_stage,
            "year": enrolled_subject.source_year or enrolled_subject.child.school_year,
            "lessons_per_week": enrolled_subject.lessons_per_week,
            "days_of_week": enrolled_subject.days_of_week or [0, 1, 2, 3, 4],
            "colour_hex": enrolled_subject.colour_hex,
            "source": "csv"
            if (enrolled_subject.source_year or enrolled_subject.source_subject_name)
            else "oak",
            "source_subject_name": enrolled_subject.source_subject_name or enrolled_subject.subject_name,
            "source_year": enrolled_subject.source_year,
            "is_active": True,
        }
        existing = CourseSubjectConfig.objects.filter(
            course=legacy_item.course,
            subject_name=enrolled_subject.subject_name,
        ).first()
        if existing is not None:
            return existing, False
        if dry_run:
            return None, True
        return (
            CourseSubjectConfig.objects.create(
                course=legacy_item.course,
                subject_name=enrolled_subject.subject_name,
                **defaults,
            ),
            True,
        )

    def _build_plan_item_from_legacy(self, legacy_item, dry_run=False):
        item_kind = legacy_item.template.item_kind
        if item_kind == "lesson":
            course_subject, created_config = self._infer_course_subject_config(
                legacy_item, dry_run=dry_run
            )
            if course_subject is None and dry_run:
                return self.DRY_RUN_SENTINEL, created_config
            if course_subject is None:
                return None, created_config
            if dry_run:
                return self.DRY_RUN_SENTINEL, created_config
            return (
                create_plan_item(
                    course=legacy_item.course,
                    item_type=PlanItem.ITEM_TYPE_LESSON,
                    week_number=legacy_item.week_number,
                    day_number=legacy_item.day_number,
                    name=legacy_item.template.name,
                    description=legacy_item.template.description,
                    order=legacy_item.order,
                    course_subject=course_subject,
                    curriculum_lesson=getattr(legacy_item.scheduled_lesson, "lesson", None),
                ),
                created_config,
            )
        if item_kind == "activity":
            if dry_run:
                return self.DRY_RUN_SENTINEL, False
            return (
                create_plan_item(
                    course=legacy_item.course,
                    item_type=PlanItem.ITEM_TYPE_ACTIVITY,
                    week_number=legacy_item.week_number,
                    day_number=legacy_item.day_number,
                    name=legacy_item.template.name,
                    description=legacy_item.template.description,
                    order=legacy_item.order,
                    due_offset_days=legacy_item.due_in_days,
                ),
                False,
            )
        if legacy_item.template.assignment_type is None:
            return None, False
        if dry_run:
            return self.DRY_RUN_SENTINEL, False
        return (
            create_plan_item(
                course=legacy_item.course,
                item_type=PlanItem.ITEM_TYPE_ASSIGNMENT,
                week_number=legacy_item.week_number,
                day_number=legacy_item.day_number,
                name=legacy_item.template.name,
                description=legacy_item.template.description,
                order=legacy_item.order,
                assignment_type=legacy_item.template.assignment_type,
                is_graded=legacy_item.template.is_graded,
                due_offset_days=legacy_item.due_in_days,
            ),
            False,
        )

    def _repair_scheduled_lesson(self, legacy_item, canonical, dry_run=False):
        scheduled_lesson = legacy_item.scheduled_lesson
        if scheduled_lesson is None or canonical is None or canonical is self.DRY_RUN_SENTINEL:
            return 0
        updated = False
        if scheduled_lesson.plan_item_id != canonical.id:
            scheduled_lesson.plan_item = canonical
            updated = True
        course_subject = getattr(getattr(canonical, "lesson_detail", None), "course_subject", None)
        if course_subject and scheduled_lesson.course_subject_id != course_subject.id:
            scheduled_lesson.course_subject = course_subject
            updated = True
        if updated and not dry_run:
            scheduled_lesson.save(update_fields=["plan_item", "course_subject"])
        return int(updated)

    def _repair_assignments(self, legacy_item, canonical, dry_run=False):
        if canonical is None or canonical is self.DRY_RUN_SENTINEL:
            return 0
        repaired = 0
        for assignment in StudentAssignment.objects.filter(plan_item=legacy_item):
            if assignment.new_plan_item_id != canonical.id:
                repaired += 1
                if not dry_run:
                    assignment.new_plan_item = canonical
                    assignment.save(update_fields=["new_plan_item"])
        return repaired

    def _repair_activities(self, legacy_item, canonical, dry_run=False):
        if canonical is None or canonical is self.DRY_RUN_SENTINEL:
            return 0
        repaired = 0
        for progress in ActivityProgress.objects.filter(plan_item=legacy_item):
            if progress.new_plan_item_id != canonical.id:
                repaired += 1
                if not dry_run:
                    progress.new_plan_item = canonical
                    progress.save(update_fields=["new_plan_item"])
        return repaired
