"""Service functions for planning CRUD operations.

Extracted from plan_course_view to enable testable, reusable business logic.
"""

import datetime

from django.db import models, transaction
from django.db.models import Max
from django.shortcuts import get_object_or_404
from django.utils import timezone

from courses.models import AssignmentType, CourseEnrollment, CourseSubjectConfig
from curriculum.models import Lesson
from scheduler.models import EnrolledSubject, ScheduledLesson, Vacation

from .models import (
    ActivityProgress,
    ActivityProgressAttachment,
    AssignmentAttachment,
    AssignmentPlanItem,
    CourseAssignmentTemplate,
    StudentAssignment,
    PlanItem,
    LessonPlanDetail,
    AssignmentPlanDetail,
    ActivityPlanDetail,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def schedule_date_from_week_day(child, week_number, day_number):
    """Compute a calendar date from a child's academic year start + grid position."""
    return child.academic_year_start + datetime.timedelta(
        days=(week_number - 1) * 7 + (day_number - 1)
    )


def lesson_query_for_subject(child, enrolled_subject):
    """Return a queryset of Lesson rows for a given child + enrolled subject."""
    source_subject = (enrolled_subject.source_subject_name or "").strip()
    lesson_subject = source_subject or enrolled_subject.subject_name
    lesson_year = enrolled_subject.source_year or child.school_year
    return Lesson.objects.filter(
        subject_name=lesson_subject,
        year=lesson_year,
    ).order_by("unit_slug", "lesson_number")


def next_unscheduled_lesson(child, enrolled_subject):
    """Return the next curriculum Lesson not yet scheduled for this child+subject."""
    scheduled_ids = ScheduledLesson.objects.filter(
        child=child,
        enrolled_subject=enrolled_subject,
    ).values_list("lesson_id", flat=True)
    return (
        lesson_query_for_subject(child, enrolled_subject)
        .exclude(id__in=scheduled_ids)
        .first()
    )


def _normalized_course_weekdays(course):
    return list(range(max(course.frequency_days, 1)))


def _normalize_day_values(course, raw_days):
    valid_days = set(_normalized_course_weekdays(course))
    normalized = sorted(
        {
            int(day)
            for day in (raw_days or [])
            if str(day).strip().lstrip("-").isdigit() and int(day) in valid_days
        }
    )
    return normalized or _normalized_course_weekdays(course)


def _normalize_lessons_per_week(raw_value):
    try:
        parsed = int(raw_value)
    except (TypeError, ValueError):
        parsed = 3
    return max(1, min(10, parsed))


def _sync_legacy_bridge_template(plan_item, template=None):
    item_kind = {
        PlanItem.ITEM_TYPE_LESSON: CourseAssignmentTemplate.ITEM_KIND_LESSON,
        PlanItem.ITEM_TYPE_ASSIGNMENT: CourseAssignmentTemplate.ITEM_KIND_ASSIGNMENT,
        PlanItem.ITEM_TYPE_ACTIVITY: CourseAssignmentTemplate.ITEM_KIND_ACTIVITY,
    }.get(plan_item.item_type)
    if item_kind is None:
        raise ValueError(f"unsupported plan item type for legacy bridge: {plan_item.item_type}")

    assignment_type = None
    due_offset_days = 0
    is_graded = False

    if plan_item.item_type == PlanItem.ITEM_TYPE_ASSIGNMENT:
        detail = getattr(plan_item, "assignment_detail", None)
        if detail is None or detail.assignment_type is None:
            raise ValueError("assignment plan items require assignment_detail.assignment_type")
        assignment_type = detail.assignment_type
        due_offset_days = detail.due_offset_days
        is_graded = detail.is_graded
    elif plan_item.item_type == PlanItem.ITEM_TYPE_ACTIVITY:
        detail = getattr(plan_item, "activity_detail", None)
        due_offset_days = detail.due_offset_days if detail else 0

    if template is None:
        template = CourseAssignmentTemplate.objects.filter(
            course=plan_item.course,
            item_kind=item_kind,
            name=plan_item.name,
            assignment_type=assignment_type,
        ).first()
    if template is None:
        template = CourseAssignmentTemplate.objects.create(
            course=plan_item.course,
            item_kind=item_kind,
            name=plan_item.name,
            assignment_type=assignment_type,
            description=plan_item.description or "",
            is_graded=is_graded,
            due_offset_days=due_offset_days,
            order=plan_item.order,
        )
        return template

    changed_fields = set()
    if template.item_kind != item_kind:
        template.item_kind = item_kind
        changed_fields.add("item_kind")
    if template.assignment_type_id != getattr(assignment_type, "id", None):
        template.assignment_type = assignment_type
        changed_fields.add("assignment_type")
    if template.name != plan_item.name:
        template.name = plan_item.name
        changed_fields.add("name")
    if template.description != (plan_item.description or ""):
        template.description = plan_item.description or ""
        changed_fields.add("description")
    if template.is_graded != is_graded:
        template.is_graded = is_graded
        changed_fields.add("is_graded")
    if template.due_offset_days != due_offset_days:
        template.due_offset_days = due_offset_days
        changed_fields.add("due_offset_days")
    if template.order != plan_item.order:
        template.order = plan_item.order
        changed_fields.add("order")
    if changed_fields:
        template.save(update_fields=list(changed_fields))

    return template


def _get_or_create_legacy_bridge_plan_item(plan_item, bridge_item=None, notes=""):
    template = _sync_legacy_bridge_template(
        plan_item,
        template=bridge_item.template if bridge_item is not None else None,
    )

    if bridge_item is None:
        bridge_item = AssignmentPlanItem.objects.filter(
            course=plan_item.course,
            template=template,
            week_number=plan_item.week_number,
            day_number=plan_item.day_number,
            order=plan_item.order,
        ).first()
    if bridge_item is None:
        bridge_item = AssignmentPlanItem.objects.create(
            course=plan_item.course,
            template=template,
            week_number=plan_item.week_number,
            day_number=plan_item.day_number,
            order=plan_item.order,
            due_in_days=0,
            notes=notes or "",
        )
        return bridge_item

    update_fields = set()
    due_in_days = 0
    if plan_item.item_type == PlanItem.ITEM_TYPE_ASSIGNMENT:
        due_in_days = getattr(plan_item.assignment_detail, "due_offset_days", 0)
    elif plan_item.item_type == PlanItem.ITEM_TYPE_ACTIVITY:
        due_in_days = getattr(plan_item.activity_detail, "due_offset_days", 0)

    if bridge_item.template_id != template.id:
        bridge_item.template = template
        update_fields.add("template")
    if bridge_item.due_in_days != due_in_days:
        bridge_item.due_in_days = due_in_days
        update_fields.add("due_in_days")
    if bridge_item.week_number != plan_item.week_number:
        bridge_item.week_number = plan_item.week_number
        update_fields.add("week_number")
    if bridge_item.day_number != plan_item.day_number:
        bridge_item.day_number = plan_item.day_number
        update_fields.add("day_number")
    if bridge_item.order != plan_item.order:
        bridge_item.order = plan_item.order
        update_fields.add("order")
    if bridge_item.notes != (notes or ""):
        bridge_item.notes = notes or ""
        update_fields.add("notes")
    if update_fields:
        bridge_item.save(update_fields=list(update_fields))

    return bridge_item


def ensure_plan_item_for_legacy(legacy_item):
    """Return the canonical PlanItem for a legacy AssignmentPlanItem, creating one if needed."""
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

    if linked_ids:
        canonical = PlanItem.objects.filter(pk=next(iter(linked_ids))).first()
        if canonical is not None:
            return canonical

    item_type = {
        CourseAssignmentTemplate.ITEM_KIND_LESSON: PlanItem.ITEM_TYPE_LESSON,
        CourseAssignmentTemplate.ITEM_KIND_ACTIVITY: PlanItem.ITEM_TYPE_ACTIVITY,
        CourseAssignmentTemplate.ITEM_KIND_ASSIGNMENT: PlanItem.ITEM_TYPE_ASSIGNMENT,
    }.get(legacy_item.template.item_kind, PlanItem.ITEM_TYPE_ASSIGNMENT)

    canonical = PlanItem.objects.filter(
        course=legacy_item.course,
        item_type=item_type,
        week_number=legacy_item.week_number,
        day_number=legacy_item.day_number,
        order=legacy_item.order,
        name=legacy_item.template.name,
    ).first()
    if canonical is not None:
        return canonical

    detail_kwargs = {}
    if item_type == PlanItem.ITEM_TYPE_ASSIGNMENT:
        if legacy_item.template.assignment_type is None:
            raise ValueError("legacy assignment plan item is missing assignment type")
        detail_kwargs.update(
            assignment_type=legacy_item.template.assignment_type,
            is_graded=legacy_item.template.is_graded,
            due_offset_days=legacy_item.due_in_days,
        )
    elif item_type == PlanItem.ITEM_TYPE_ACTIVITY:
        detail_kwargs.update(due_offset_days=legacy_item.due_in_days)
    else:
        enrolled_subject = legacy_item.lesson_enrolled_subject or getattr(
            legacy_item.scheduled_lesson, "enrolled_subject", None
        )
        course_subject = getattr(legacy_item.scheduled_lesson, "course_subject", None)
        if course_subject is None and enrolled_subject is not None:
            course_subject = CourseSubjectConfig.objects.filter(
                course=legacy_item.course
            ).filter(
                models.Q(subject_name__iexact=enrolled_subject.subject_name)
                | models.Q(
                    source_subject_name__iexact=(
                        enrolled_subject.source_subject_name or enrolled_subject.subject_name
                    )
                )
            ).first()
        if course_subject is None:
            raise ValueError("legacy lesson plan item is missing a course subject mapping")
        detail_kwargs.update(
            course_subject=course_subject,
            curriculum_lesson=getattr(legacy_item.scheduled_lesson, "lesson", None),
        )

    canonical = create_plan_item(
        course=legacy_item.course,
        item_type=item_type,
        week_number=legacy_item.week_number,
        day_number=legacy_item.day_number,
        name=legacy_item.template.name,
        description=legacy_item.template.description,
        order=legacy_item.order,
        **detail_kwargs,
    )
    _get_or_create_legacy_bridge_plan_item(
        canonical, bridge_item=legacy_item, notes=legacy_item.notes
    )
    if legacy_item.scheduled_lesson_id:
        legacy_item.scheduled_lesson.plan_item = canonical
        update_fields = ["plan_item"]
        if getattr(getattr(canonical, "lesson_detail", None), "course_subject", None):
            legacy_item.scheduled_lesson.course_subject = canonical.lesson_detail.course_subject
            update_fields.append("course_subject")
        legacy_item.scheduled_lesson.save(update_fields=update_fields)
    StudentAssignment.objects.filter(plan_item=legacy_item).update(new_plan_item=canonical)
    ActivityProgress.objects.filter(plan_item=legacy_item).update(new_plan_item=canonical)
    return canonical


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


def delete_plan_item_legacy(plan_item):
    """Delete a plan item and its template, cleaning up any scheduled lesson."""
    template = plan_item.template
    if plan_item.scheduled_lesson_id:
        plan_item.scheduled_lesson.delete()
    plan_item.delete()
    template.delete()


# ---------------------------------------------------------------------------
# Create / Update
# ---------------------------------------------------------------------------


def _resolve_lesson_context(post_data, active_enrollments, active_child_ids):
    """Validate and resolve lesson child + enrolled subject from POST data.

    Returns (child, enrolled_subject, error_message).
    """
    lesson_child_id = _safe_int(post_data.get("lesson_child_id"), None)
    lesson_subject_id = _safe_int(post_data.get("lesson_subject_id"), None)

    if lesson_child_id not in active_child_ids:
        return None, None, "Please select a valid student for this lesson."

    selected_child = None
    for enrollment in active_enrollments:
        if enrollment.child_id == lesson_child_id:
            selected_child = enrollment.child
            break

    selected_subject = EnrolledSubject.objects.filter(
        pk=lesson_subject_id,
        child=selected_child,
        is_active=True,
    ).first()
    if selected_subject is None:
        return None, None, "Please select a valid subject for this lesson."

    return selected_child, selected_subject, None


def _create_or_update_scheduled_lesson(
    plan_item, child, enrolled_subject, week_number, day_number, is_edit=False
):
    """Create or update a ScheduledLesson linked to a plan item.

    Returns (scheduled_lesson, error_message).
    """
    scheduled_date = schedule_date_from_week_day(child, week_number, day_number)

    if is_edit:
        existing = plan_item.scheduled_lesson
        if (
            existing
            and existing.child_id == child.id
            and existing.enrolled_subject_id == enrolled_subject.id
        ):
            existing.scheduled_date = scheduled_date
            existing.save(update_fields=["scheduled_date"])
            return existing, None
        else:
            if existing:
                existing.delete()

    next_lesson = next_unscheduled_lesson(child, enrolled_subject)
    if next_lesson is None:
        return None, "No remaining lessons are available for that subject."

    next_order = (
        ScheduledLesson.objects.filter(
            child=child,
            scheduled_date=scheduled_date,
        ).aggregate(max_order=Max("order_on_day"))["max_order"]
        or -1
    )
    scheduled_lesson = ScheduledLesson.objects.create(
        child=child,
        lesson=next_lesson,
        enrolled_subject=enrolled_subject,
        scheduled_date=scheduled_date,
        order_on_day=next_order + 1,
    )
    return scheduled_lesson, None


def create_plan_item_from_post(course, post_data, files, active_enrollments):
    """Create a new plan item (template + plan item + per-student records).

    Returns (plan_item, error_message). If error_message is not None,
    plan_item may be None and the caller should show the error.
    """
    active_enrollment_ids = {e.id for e in active_enrollments}
    active_child_ids = {e.child_id for e in active_enrollments}

    template_name = post_data.get("assignment_name", "").strip()
    item_kind = (post_data.get("item_kind", "assignment")).strip().lower()
    if item_kind not in ("assignment", "lesson", "activity"):
        item_kind = "assignment"

    is_assignment = item_kind == "assignment"
    is_lesson = item_kind == "lesson"
    is_activity = item_kind == "activity"

    type_id = post_data.get("assignment_type") if is_assignment else None
    week_number = _safe_int(post_data.get("week_number", 1), 1)
    day_number = _safe_int(post_data.get("day_number", 1), 1)
    due_in_days = _safe_int(post_data.get("due_in_days", 0), 0)
    description = post_data.get("description", "").strip()
    teacher_notes = post_data.get("teacher_notes", "").strip()
    is_graded = post_data.get("is_graded") == "on" if is_assignment else False

    # Validate assignment type
    if is_assignment and not type_id:
        return None, "Please select an assignment type."

    assignment_type = None
    if is_assignment:
        assignment_type = get_object_or_404(
            AssignmentType, pk=type_id, course=course, is_hidden=False
        )

    # Validate lesson context
    lesson_child = None
    lesson_subject = None
    if is_lesson:
        lesson_child, lesson_subject, err = _resolve_lesson_context(
            post_data, active_enrollments, active_child_ids
        )
        if err:
            return None, err

    if not template_name:
        return None, None  # No name provided, no-op

    # Create template + plan item
    template = CourseAssignmentTemplate.objects.create(
        course=course,
        item_kind=item_kind,
        assignment_type=assignment_type,
        name=template_name,
        description=description,
        is_graded=is_graded,
        due_offset_days=due_in_days if is_assignment else 0,
        order=0,
    )
    plan_item = AssignmentPlanItem.objects.create(
        course=course,
        template=template,
        week_number=week_number,
        day_number=day_number,
        due_in_days=due_in_days if is_assignment else 0,
        order=0,
        notes=teacher_notes,
    )

    # Lesson scheduling
    if is_lesson:
        scheduled_lesson, err = _create_or_update_scheduled_lesson(
            plan_item, lesson_child, lesson_subject, week_number, day_number
        )
        if err:
            plan_item.delete()
            template.delete()
            return None, err
        plan_item.lesson_child = lesson_child
        plan_item.lesson_enrolled_subject = lesson_subject
        plan_item.scheduled_lesson = scheduled_lesson
        plan_item.save(
            update_fields=[
                "lesson_child",
                "lesson_enrolled_subject",
                "scheduled_lesson",
            ]
        )

    # Attachments
    _save_attachments(plan_item, files)

    # Student assignments
    if is_assignment:
        selected_ids = _parse_enrollment_selection(
            post_data,
            "assign_enrollment_selection_present",
            "assign_enrollment_ids",
            active_enrollment_ids,
        )
        _sync_student_assignments(
            plan_item, active_enrollments, selected_ids, week_number, day_number,
            due_in_days, post_data, is_create=True
        )
    else:
        StudentAssignment.objects.filter(plan_item=plan_item).delete()

    # Activity progress
    if is_activity:
        selected_ids = _parse_enrollment_selection(
            post_data,
            "activity_enrollment_selection_present",
            "activity_enrollment_ids",
            active_enrollment_ids,
        )
        _sync_activity_progress(
            plan_item, active_enrollments, selected_ids, post_data, files
        )
    else:
        ActivityProgress.objects.filter(plan_item=plan_item).delete()

    return plan_item, None


def update_plan_item_from_post(plan_item, course, post_data, files, active_enrollments):
    """Update an existing plan item from POST data.

    Returns (plan_item, error_message).
    """
    active_enrollment_ids = {e.id for e in active_enrollments}
    active_child_ids = {e.child_id for e in active_enrollments}

    template_name = post_data.get("assignment_name", "").strip()
    item_kind = (post_data.get("item_kind", "assignment")).strip().lower()
    if item_kind not in ("assignment", "lesson", "activity"):
        item_kind = "assignment"

    is_assignment = item_kind == "assignment"
    is_lesson = item_kind == "lesson"
    is_activity = item_kind == "activity"

    type_id = post_data.get("assignment_type") if is_assignment else None
    week_number = _safe_int(post_data.get("week_number", 1), 1)
    day_number = _safe_int(post_data.get("day_number", 1), 1)
    due_in_days = _safe_int(post_data.get("due_in_days", 0), 0)
    description = post_data.get("description", "").strip()
    teacher_notes = post_data.get("teacher_notes", "").strip()
    is_graded = post_data.get("is_graded") == "on" if is_assignment else False

    if is_assignment and not type_id:
        return plan_item, "Please select an assignment type."

    assignment_type = None
    if is_assignment:
        assignment_type = get_object_or_404(
            AssignmentType, pk=type_id, course=course, is_hidden=False
        )

    lesson_child = None
    lesson_subject = None
    if is_lesson:
        lesson_child, lesson_subject, err = _resolve_lesson_context(
            post_data, active_enrollments, active_child_ids
        )
        if err:
            return plan_item, err

    if not template_name:
        return plan_item, None

    # Update template
    template = plan_item.template
    template.item_kind = item_kind
    template.assignment_type = assignment_type
    template.name = template_name
    template.description = description
    template.is_graded = is_graded
    template.due_offset_days = due_in_days if is_assignment else 0
    template.save()

    # Update plan item
    plan_item.week_number = week_number
    plan_item.day_number = day_number
    plan_item.due_in_days = due_in_days if is_assignment else 0
    plan_item.notes = teacher_notes

    # Handle lesson scheduling
    if is_lesson:
        scheduled_lesson, err = _create_or_update_scheduled_lesson(
            plan_item, lesson_child, lesson_subject,
            week_number, day_number, is_edit=True
        )
        if err:
            return plan_item, err
        plan_item.lesson_child = lesson_child
        plan_item.lesson_enrolled_subject = lesson_subject
        plan_item.scheduled_lesson = scheduled_lesson
    else:
        if plan_item.scheduled_lesson_id:
            plan_item.scheduled_lesson.delete()
        plan_item.lesson_child = None
        plan_item.lesson_enrolled_subject = None
        plan_item.scheduled_lesson = None

    plan_item.save()

    # Attachments
    _save_attachments(plan_item, files)

    # Student assignments
    if is_assignment:
        selected_ids = _parse_enrollment_selection(
            post_data,
            "assign_enrollment_selection_present",
            "assign_enrollment_ids",
            active_enrollment_ids,
        )
        _sync_student_assignments(
            plan_item, active_enrollments, selected_ids, week_number, day_number,
            due_in_days, post_data, is_create=False
        )
    else:
        StudentAssignment.objects.filter(plan_item=plan_item).delete()

    # Activity progress
    if is_activity:
        selected_ids = _parse_enrollment_selection(
            post_data,
            "activity_enrollment_selection_present",
            "activity_enrollment_ids",
            active_enrollment_ids,
        )
        _sync_activity_progress(
            plan_item, active_enrollments, selected_ids, post_data, files
        )
    else:
        ActivityProgress.objects.filter(plan_item=plan_item).delete()

    return plan_item, None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_enrollment_selection(post_data, presence_key, ids_key, active_enrollment_ids):
    """Parse enrollment selection checkboxes from POST data."""
    if post_data.get(presence_key) == "1":
        raw_ids = {_safe_int(v, -1) for v in post_data.getlist(ids_key)}
        return {eid for eid in raw_ids if eid in active_enrollment_ids}
    return set(active_enrollment_ids)


def _save_attachments(plan_item, files):
    """Save uploaded attachments for a plan item."""
    for attachment in files.getlist("attachments"):
        AssignmentAttachment.objects.create(
            plan_item=plan_item,
            file=attachment,
            original_name=attachment.name,
        )


def _sync_student_assignments(
    plan_item, active_enrollments, selected_ids,
    week_number, day_number, due_in_days, post_data, is_create=True
):
    """Create, update, or remove StudentAssignment rows for a plan item."""
    for enrollment in active_enrollments:
        base_date = enrollment.start_date + datetime.timedelta(
            days=(week_number - 1) * 7 + (day_number - 1)
        )
        due_date = base_date + datetime.timedelta(days=due_in_days)

        if enrollment.id in selected_ids:
            if not is_create:
                student_assignment, _ = StudentAssignment.objects.get_or_create(
                    enrollment=enrollment,
                    plan_item=plan_item,
                    defaults={"due_date": due_date, "status": "pending"},
                )
                updates = []
                if student_assignment.due_date != due_date:
                    student_assignment.due_date = due_date
                    updates.append("due_date")
                status_value = post_data.get(
                    f"student_status_{student_assignment.id}",
                    student_assignment.status,
                )
                if (
                    status_value in {"pending", "complete"}
                    and student_assignment.status != status_value
                ):
                    student_assignment.status = status_value
                    student_assignment.completed_at = (
                        timezone.now() if status_value == "complete" else None
                    )
                    updates.extend(["status", "completed_at"])
                if updates:
                    student_assignment.save(update_fields=updates)
            else:
                StudentAssignment.objects.create(
                    enrollment=enrollment,
                    plan_item=plan_item,
                    due_date=due_date,
                    status="pending",
                )
        else:
            StudentAssignment.objects.filter(
                enrollment=enrollment,
                plan_item=plan_item,
            ).delete()


def _sync_activity_progress(
    plan_item, active_enrollments, selected_ids, post_data, files
):
    """Create, update, or remove ActivityProgress rows for a plan item."""
    for enrollment in active_enrollments:
        if enrollment.id in selected_ids:
            progress, _ = ActivityProgress.objects.get_or_create(
                enrollment=enrollment,
                plan_item=plan_item,
            )
            status_value = post_data.get(
                f"activity_status_{enrollment.id}",
                progress.status,
            )
            if status_value not in {"pending", "complete"}:
                status_value = "pending"
            progress.notes = post_data.get(
                f"activity_notes_{enrollment.id}",
                progress.notes,
            ).strip()
            progress.status = status_value
            progress.completed_at = (
                timezone.now() if status_value == "complete" else None
            )
            progress.save()

            external_url = post_data.get(
                f"activity_link_{enrollment.id}", ""
            ).strip()
            if external_url:
                ActivityProgressAttachment.objects.create(
                    progress=progress,
                    external_url=external_url,
                )
            for attachment in files.getlist(f"activity_files_{enrollment.id}"):
                ActivityProgressAttachment.objects.create(
                    progress=progress,
                    file=attachment,
                    original_name=attachment.name,
                )
        else:
            ActivityProgress.objects.filter(
                enrollment=enrollment,
                plan_item=plan_item,
            ).delete()


# ---------------------------------------------------------------------------
# New PlanItem-based helpers (Phase 3)
# ---------------------------------------------------------------------------


def compute_enrollment_calendar_date(enrollment, week_number, day_number, due_offset_days=0):
    """Compute a calendar date from an enrollment's start date + grid position."""
    return enrollment.start_date + datetime.timedelta(
        days=(week_number - 1) * 7 + (day_number - 1) + due_offset_days
    )


def create_plan_item(
    course,
    item_type,
    week_number,
    day_number,
    name,
    description="",
    order=0,
    is_active=True,
    **detail_kwargs,
):
    """Create a PlanItem and its associated detail row inside a transaction.

    detail_kwargs vary by item_type:
    - lesson: requires `course_subject` (CourseSubjectConfig instance), optional `curriculum_lesson`.
    - assignment: requires `assignment_type` (AssignmentType instance), optional `is_graded` and `due_offset_days`.
    - activity: optional `goal`, `objective`, `course_subject`, `unit_title`, `due_offset_days`.
    """
    with transaction.atomic():
        plan_item = PlanItem.objects.create(
            course=course,
            item_type=item_type,
            week_number=week_number,
            day_number=day_number,
            name=name,
            description=description or "",
            order=order,
            is_active=is_active,
        )

        if item_type == PlanItem.ITEM_TYPE_LESSON:
            course_subject = detail_kwargs.get("course_subject")
            curriculum_lesson = detail_kwargs.get("curriculum_lesson")
            if not course_subject:
                raise ValueError("lesson plan items require a course_subject")
            LessonPlanDetail.objects.create(
                plan_item=plan_item,
                course_subject=course_subject,
                curriculum_lesson=curriculum_lesson,
            )

        elif item_type == PlanItem.ITEM_TYPE_ASSIGNMENT:
            assignment_type = detail_kwargs.get("assignment_type")
            is_graded = detail_kwargs.get("is_graded", False)
            due_offset_days = detail_kwargs.get("due_offset_days", 0)
            if not assignment_type:
                raise ValueError("assignment plan items require an assignment_type")
            AssignmentPlanDetail.objects.create(
                plan_item=plan_item,
                assignment_type=assignment_type,
                is_graded=is_graded,
                due_offset_days=due_offset_days,
            )

        elif item_type == PlanItem.ITEM_TYPE_ACTIVITY:
            goal = detail_kwargs.get("goal", "")
            objective = detail_kwargs.get("objective", "")
            activity_course_subject = detail_kwargs.get("course_subject")
            unit_title = detail_kwargs.get("unit_title", "")
            due_offset_days = detail_kwargs.get("due_offset_days", 0)
            ActivityPlanDetail.objects.create(
                plan_item=plan_item,
                goal=goal,
                objective=objective,
                course_subject=activity_course_subject,
                unit_title=unit_title,
                due_offset_days=due_offset_days,
            )

        else:
            # Unknown item type — rollback and raise
            raise ValueError(f"Unknown PlanItem type: {item_type}")

    return plan_item


def update_plan_item(plan_item, **fields):
    """Update a PlanItem and its detail row. Fields are the same as create_plan_item args."""
    allowed_base = {
        "week_number",
        "day_number",
        "name",
        "description",
        "order",
        "is_active",
    }
    updated = False
    for k, v in list(fields.items()):
        if k in allowed_base:
            setattr(plan_item, k, v)
            updated = True

    if updated:
        plan_item.save()

    # Update details
    if plan_item.item_type == PlanItem.ITEM_TYPE_LESSON:
        detail = getattr(plan_item, "lesson_detail", None)
        if detail is None:
            # create if missing
            course_subject = fields.get("course_subject")
            curriculum_lesson = fields.get("curriculum_lesson")
            if course_subject:
                LessonPlanDetail.objects.create(
                    plan_item=plan_item,
                    course_subject=course_subject,
                    curriculum_lesson=curriculum_lesson,
                )
        else:
            if "course_subject" in fields and fields.get("course_subject") is not None:
                detail.course_subject = fields.get("course_subject")
            if "curriculum_lesson" in fields:
                detail.curriculum_lesson = fields.get("curriculum_lesson")
            detail.save()

    elif plan_item.item_type == PlanItem.ITEM_TYPE_ASSIGNMENT:
        detail = getattr(plan_item, "assignment_detail", None)
        if detail is None:
            assignment_type = fields.get("assignment_type")
            if assignment_type:
                AssignmentPlanDetail.objects.create(
                    plan_item=plan_item,
                    assignment_type=assignment_type,
                    is_graded=fields.get("is_graded", False),
                    due_offset_days=fields.get("due_offset_days", 0),
                )
        else:
            if "assignment_type" in fields and fields.get("assignment_type") is not None:
                detail.assignment_type = fields.get("assignment_type")
            if "is_graded" in fields:
                detail.is_graded = fields.get("is_graded")
            if "due_offset_days" in fields:
                detail.due_offset_days = fields.get("due_offset_days")
            detail.save()

    elif plan_item.item_type == PlanItem.ITEM_TYPE_ACTIVITY:
        detail = getattr(plan_item, "activity_detail", None)
        if detail is None:
            ActivityPlanDetail.objects.create(
                plan_item=plan_item,
                goal=fields.get("goal", ""),
                objective=fields.get("objective", ""),
                course_subject=fields.get("course_subject"),
                unit_title=fields.get("unit_title", ""),
                due_offset_days=fields.get("due_offset_days", 0),
            )
        else:
            for attr in ("goal", "objective", "unit_title", "due_offset_days"):
                if attr in fields:
                    setattr(detail, attr, fields.get(attr))
            if "course_subject" in fields and fields.get("course_subject") is not None:
                detail.course_subject = fields.get("course_subject")
            detail.save()

    return plan_item


def soft_delete_plan_item(plan_item):
    plan_item.is_active = False
    plan_item.save(update_fields=["is_active"])
    return plan_item


def hard_delete_plan_item(plan_item):
    plan_item.delete()


def save_plan_item_from_post(
    course,
    post_data,
    files,
    active_enrollments,
    plan_item=None,
    legacy_bridge_item=None,
):
    """Create or update a canonical PlanItem from the planning form payload."""
    active_enrollment_ids = {e.id for e in active_enrollments}
    active_child_ids = {e.child_id for e in active_enrollments}

    template_name = post_data.get("assignment_name", "").strip()
    item_kind = (post_data.get("item_kind", "assignment")).strip().lower()
    if item_kind not in ("assignment", "lesson", "activity"):
        item_kind = "assignment"
    item_type = {
        "assignment": PlanItem.ITEM_TYPE_ASSIGNMENT,
        "lesson": PlanItem.ITEM_TYPE_LESSON,
        "activity": PlanItem.ITEM_TYPE_ACTIVITY,
    }[item_kind]

    week_number = _safe_int(post_data.get("week_number", 1), 1)
    day_number = _safe_int(post_data.get("day_number", 1), 1)
    due_in_days = _safe_int(post_data.get("due_in_days", 0), 0)
    description = post_data.get("description", "").strip()
    teacher_notes = post_data.get("teacher_notes", "").strip()

    if not template_name:
        return plan_item, None

    assignment_type = None
    is_graded = False
    if item_type == PlanItem.ITEM_TYPE_ASSIGNMENT:
        type_id = post_data.get("assignment_type")
        if not type_id:
            return plan_item, "Please select an assignment type."
        assignment_type = get_object_or_404(
            AssignmentType, pk=type_id, course=course, is_hidden=False
        )
        is_graded = post_data.get("is_graded") == "on"

    selected_child = None
    selected_subject = None
    selected_enrollment = None
    course_subject = None
    if item_type == PlanItem.ITEM_TYPE_LESSON:
        selected_child, selected_subject, err = _resolve_lesson_context(
            post_data, active_enrollments, active_child_ids
        )
        if err:
            return plan_item, err
        selected_enrollment = next(
            (enrollment for enrollment in active_enrollments if enrollment.child_id == selected_child.id),
            None,
        )
        if selected_enrollment is None:
            return plan_item, "Please select a valid student for this lesson."
        source_name = selected_subject.source_subject_name or selected_subject.subject_name
        course_subject = CourseSubjectConfig.objects.filter(course=course).filter(
            models.Q(subject_name__iexact=selected_subject.subject_name)
            | models.Q(source_subject_name__iexact=source_name)
        ).first()
        if course_subject is None:
            course_subject = CourseSubjectConfig.objects.create(
                course=course,
                subject_name=selected_subject.subject_name,
                key_stage=selected_subject.key_stage,
                year=selected_subject.source_year or selected_child.school_year,
                lessons_per_week=selected_subject.lessons_per_week,
                days_of_week=selected_subject.days_of_week or _normalized_course_weekdays(course),
                colour_hex=selected_subject.colour_hex,
                source="csv"
                if (selected_subject.source_year or selected_subject.source_subject_name)
                else "oak",
                source_subject_name=source_name,
                source_year=selected_subject.source_year,
                is_active=True,
            )

    with transaction.atomic():
        if plan_item is None:
            detail_kwargs = {}
            if item_type == PlanItem.ITEM_TYPE_ASSIGNMENT:
                detail_kwargs.update(
                    assignment_type=assignment_type,
                    is_graded=is_graded,
                    due_offset_days=due_in_days,
                )
            elif item_type == PlanItem.ITEM_TYPE_ACTIVITY:
                detail_kwargs.update(due_offset_days=due_in_days)
            else:
                detail_kwargs.update(course_subject=course_subject)
            plan_item = create_plan_item(
                course=course,
                item_type=item_type,
                week_number=week_number,
                day_number=day_number,
                name=template_name,
                description=description,
                order=0,
                **detail_kwargs,
            )
        else:
            detail_kwargs = {
                "week_number": week_number,
                "day_number": day_number,
                "name": template_name,
                "description": description,
            }
            if item_type == PlanItem.ITEM_TYPE_ASSIGNMENT:
                detail_kwargs.update(
                    assignment_type=assignment_type,
                    is_graded=is_graded,
                    due_offset_days=due_in_days,
                )
            elif item_type == PlanItem.ITEM_TYPE_ACTIVITY:
                detail_kwargs.update(due_offset_days=due_in_days)
            elif item_type == PlanItem.ITEM_TYPE_LESSON:
                detail_kwargs.update(course_subject=course_subject)
            update_plan_item(plan_item, **detail_kwargs)

        legacy_bridge_item = _get_or_create_legacy_bridge_plan_item(
            plan_item,
            bridge_item=legacy_bridge_item,
            notes=teacher_notes,
        )
        _save_attachments(legacy_bridge_item, files)

        if item_type == PlanItem.ITEM_TYPE_ASSIGNMENT:
            selected_ids = _parse_enrollment_selection(
                post_data,
                "assign_enrollment_selection_present",
                "assign_enrollment_ids",
                active_enrollment_ids,
            )
            StudentAssignment.objects.filter(new_plan_item=plan_item).exclude(
                enrollment_id__in=selected_ids
            ).delete()
            for enrollment in active_enrollments:
                if enrollment.id not in selected_ids:
                    continue
                student_assignment = materialize_plan_item_for_enrollment(
                    plan_item, enrollment
                )[0]
                status_value = post_data.get(
                    f"student_status_{student_assignment.id}",
                    student_assignment.status,
                )
                if status_value in {"pending", "complete"}:
                    update_fields = []
                    if student_assignment.status != status_value:
                        student_assignment.status = status_value
                        student_assignment.completed_at = (
                            timezone.now() if status_value == "complete" else None
                        )
                        update_fields.extend(["status", "completed_at"])
                    if update_fields:
                        student_assignment.save(update_fields=update_fields)
        else:
            StudentAssignment.objects.filter(new_plan_item=plan_item).delete()

        if item_type == PlanItem.ITEM_TYPE_ACTIVITY:
            selected_ids = _parse_enrollment_selection(
                post_data,
                "activity_enrollment_selection_present",
                "activity_enrollment_ids",
                active_enrollment_ids,
            )
            ActivityProgress.objects.filter(new_plan_item=plan_item).exclude(
                enrollment_id__in=selected_ids
            ).delete()
            for enrollment in active_enrollments:
                if enrollment.id not in selected_ids:
                    continue
                progress = materialize_plan_item_for_enrollment(plan_item, enrollment)[0]
                status_value = post_data.get(
                    f"activity_status_{enrollment.id}",
                    progress.status,
                )
                if status_value not in {"pending", "complete"}:
                    status_value = "pending"
                progress.notes = post_data.get(
                    f"activity_notes_{enrollment.id}",
                    progress.notes,
                ).strip()
                progress.status = status_value
                progress.completed_at = (
                    timezone.now() if status_value == "complete" else None
                )
                progress.save()
                external_url = post_data.get(
                    f"activity_link_{enrollment.id}", ""
                ).strip()
                if external_url:
                    ActivityProgressAttachment.objects.create(
                        progress=progress,
                        external_url=external_url,
                    )
                for attachment in files.getlist(f"activity_files_{enrollment.id}"):
                    ActivityProgressAttachment.objects.create(
                        progress=progress,
                        file=attachment,
                        original_name=attachment.name,
                    )
        else:
            ActivityProgress.objects.filter(new_plan_item=plan_item).delete()

        if item_type == PlanItem.ITEM_TYPE_LESSON:
            current_lesson = getattr(getattr(plan_item, "lesson_detail", None), "curriculum_lesson", None)
            if current_lesson is None:
                current_lesson = next_unscheduled_lesson(selected_child, selected_subject)
                if current_lesson is not None:
                    update_plan_item(plan_item, curriculum_lesson=current_lesson)
            ScheduledLesson.objects.filter(plan_item=plan_item).exclude(
                child=selected_child
            ).delete()
            scheduled_items = materialize_plan_item_for_enrollment(plan_item, selected_enrollment)
            scheduled_lesson = scheduled_items[0] if scheduled_items else None
            legacy_bridge_item.lesson_child = selected_child
            legacy_bridge_item.lesson_enrolled_subject = selected_subject
            legacy_bridge_item.scheduled_lesson = scheduled_lesson
            legacy_bridge_item.save(
                update_fields=[
                    "lesson_child",
                    "lesson_enrolled_subject",
                    "scheduled_lesson",
                ]
            )
        else:
            if (
                legacy_bridge_item.lesson_child_id
                or legacy_bridge_item.lesson_enrolled_subject_id
                or legacy_bridge_item.scheduled_lesson_id
            ):
                legacy_bridge_item.lesson_child = None
                legacy_bridge_item.lesson_enrolled_subject = None
                legacy_bridge_item.scheduled_lesson = None
                legacy_bridge_item.save(
                    update_fields=[
                        "lesson_child",
                        "lesson_enrolled_subject",
                        "scheduled_lesson",
                    ]
                )

    return plan_item, None


def delete_plan_item(plan_item):
    """Delete a canonical PlanItem and its bridge/runtime rows."""
    legacy_bridge_ids = set(
        StudentAssignment.objects.filter(new_plan_item=plan_item).values_list(
            "plan_item_id", flat=True
        )
    )
    legacy_bridge_ids.update(
        ActivityProgress.objects.filter(new_plan_item=plan_item).values_list(
            "plan_item_id", flat=True
        )
    )
    if plan_item.item_type == PlanItem.ITEM_TYPE_LESSON:
        legacy_bridge = AssignmentPlanItem.objects.filter(
            course=plan_item.course,
            week_number=plan_item.week_number,
            day_number=plan_item.day_number,
            order=plan_item.order,
            template__item_kind=CourseAssignmentTemplate.ITEM_KIND_LESSON,
            template__name=plan_item.name,
        ).first()
        if legacy_bridge is not None:
            legacy_bridge_ids.add(legacy_bridge.id)

    ScheduledLesson.objects.filter(plan_item=plan_item).delete()
    StudentAssignment.objects.filter(new_plan_item=plan_item).delete()
    ActivityProgress.objects.filter(new_plan_item=plan_item).delete()
    plan_item.delete()

    templates_to_check = []
    for bridge_id in legacy_bridge_ids:
        bridge_item = AssignmentPlanItem.objects.filter(pk=bridge_id).select_related("template").first()
        if bridge_item is None:
            continue
        templates_to_check.append(bridge_item.template_id)
        bridge_item.delete()
    for template_id in templates_to_check:
        template = CourseAssignmentTemplate.objects.filter(pk=template_id).first()
        if template is not None and not template.plan_items.exists():
            template.delete()


def materialize_plan_item_for_enrollment(plan_item, enrollment):
    """Materialize plan item for a single CourseEnrollment.

    Creates real child-level rows for all supported plan-item types while
    preserving the legacy bridge fields required by the existing runtime.
    """
    created = []

    if plan_item.item_type == PlanItem.ITEM_TYPE_LESSON:
        # find enrolled subject matching the course_subject
        course_subject = plan_item.lesson_detail.course_subject
        child = enrollment.child
        enrolled_qs = EnrolledSubject.objects.filter(child=child, is_active=True)
        matched = None
        source_key = (course_subject.source_subject_name or "").strip().lower()
        target_name = (course_subject.subject_name or "").strip().lower()
        for es in enrolled_qs:
            if source_key and (es.source_subject_name or "").strip().lower() == source_key:
                matched = es
                break
            if (es.subject_name or "").strip().lower() == target_name:
                matched = es
                break

        if not matched:
            return created

        scheduled_date = compute_enrollment_calendar_date(
            enrollment, plan_item.week_number, plan_item.day_number
        )

        existing = ScheduledLesson.objects.filter(
            child=child,
            plan_item=plan_item,
        ).first()

        lesson = getattr(plan_item.lesson_detail, "curriculum_lesson", None)
        if lesson is None and existing is not None:
            lesson = existing.lesson
        if lesson is None:
            lesson = next_unscheduled_lesson(child, matched)
        if lesson is None:
            return created

        if existing is None:
            next_order = (
                ScheduledLesson.objects.filter(
                    child=child, scheduled_date=scheduled_date
                ).aggregate(max_order=Max("order_on_day"))["max_order"]
                or -1
            )
            scheduled = ScheduledLesson.objects.create(
                child=child,
                lesson=lesson,
                enrolled_subject=matched,
                scheduled_date=scheduled_date,
                order_on_day=next_order + 1,
                plan_item=plan_item,
                course_subject=course_subject,
            )
        else:
            scheduled = existing
            update_fields = []
            if scheduled.lesson_id != lesson.id:
                scheduled.lesson = lesson
                update_fields.append("lesson")
            if scheduled.enrolled_subject_id != matched.id:
                scheduled.enrolled_subject = matched
                update_fields.append("enrolled_subject")
            if scheduled.scheduled_date != scheduled_date:
                scheduled.scheduled_date = scheduled_date
                update_fields.append("scheduled_date")
            if scheduled.course_subject_id != course_subject.id:
                scheduled.course_subject = course_subject
                update_fields.append("course_subject")
            if update_fields:
                scheduled.save(update_fields=update_fields)
        created.append(scheduled)
    elif plan_item.item_type == PlanItem.ITEM_TYPE_ASSIGNMENT:
        legacy_plan_item = _get_or_create_legacy_bridge_plan_item(plan_item)
        due_offset_days = getattr(plan_item.assignment_detail, "due_offset_days", 0)
        due_date = compute_enrollment_calendar_date(
            enrollment,
            plan_item.week_number,
            plan_item.day_number,
            due_offset_days=due_offset_days,
        )
        student_assignment, _ = StudentAssignment.objects.get_or_create(
            enrollment=enrollment,
            plan_item=legacy_plan_item,
            defaults={
                "due_date": due_date,
                "status": "pending",
                "new_plan_item": plan_item,
            },
        )
        update_fields = []
        if student_assignment.due_date != due_date:
            student_assignment.due_date = due_date
            update_fields.append("due_date")
        if student_assignment.new_plan_item_id != plan_item.id:
            student_assignment.new_plan_item = plan_item
            update_fields.append("new_plan_item")
        if update_fields:
            student_assignment.save(update_fields=update_fields)
        created.append(student_assignment)
    elif plan_item.item_type == PlanItem.ITEM_TYPE_ACTIVITY:
        legacy_plan_item = _get_or_create_legacy_bridge_plan_item(plan_item)
        progress, _ = ActivityProgress.objects.get_or_create(
            enrollment=enrollment,
            plan_item=legacy_plan_item,
            defaults={
                "status": "pending",
                "new_plan_item": plan_item,
            },
        )
        if progress.new_plan_item_id != plan_item.id:
            progress.new_plan_item = plan_item
            progress.save(update_fields=["new_plan_item"])
        created.append(progress)

    return created


def materialize_plan_item(plan_item):
    """Materialize a plan item across all active enrollments for its course.

    Returns a list of created ScheduledLesson instances and/or operation
    descriptions for assignment/activity items.
    """
    results = []
    enrollments = plan_item.course.enrollments.filter(status="active")
    for enrollment in enrollments:
        results.extend(materialize_plan_item_for_enrollment(plan_item, enrollment))
    return results


# ---------------------------------------------------------------------------
# Phase 4: Oak auto-scheduling grid generator
# ---------------------------------------------------------------------------


def create_subject_configs_from_selection(course, subject_configs_data):
    """Create or update CourseSubjectConfig rows from subject selection form data.

    Args:
        course: A Course instance.
        subject_configs_data: List of dicts, each with keys:
            - subject_name (str)
            - key_stage (str, optional)
            - year (str)
            - lessons_per_week (int)
            - days_of_week (list of int)
            - colour_hex (str, optional)
            - source (str, default "oak")
            - source_subject_name (str, optional)
            - source_year (str, optional)

    Returns:
        List of CourseSubjectConfig instances (created or updated).
    """
    if not subject_configs_data:
        raise ValueError("at least one subject configuration is required")

    configs = []
    for data in subject_configs_data:
        subject_name = data["subject_name"].strip()
        if not subject_name:
            continue
        normalized_days = _normalize_day_values(course, data.get("days_of_week", []))
        lessons_per_week = _normalize_lessons_per_week(data.get("lessons_per_week", 3))
        source = data.get("source", "oak")
        if source not in dict(CourseSubjectConfig.SOURCE_CHOICES):
            source = "oak"
        config, _ = CourseSubjectConfig.objects.update_or_create(
            course=course,
            subject_name=subject_name,
            defaults={
                "key_stage": data.get("key_stage", ""),
                "year": data.get("year", ""),
                "lessons_per_week": lessons_per_week,
                "days_of_week": normalized_days,
                "colour_hex": data.get("colour_hex", "#6c757d"),
                "source": source,
                "source_subject_name": data.get("source_subject_name", ""),
                "source_year": data.get("source_year", ""),
                "is_active": True,
            },
        )
        configs.append(config)
    return configs


def generate_plan_grid(course, subject_configs=None):
    """Place Oak curriculum lessons into the course planning grid.

    Uses the same round-robin algorithm as scheduler/services.py:generate_schedule
    but outputs PlanItem + LessonPlanDetail rows at (week_number, day_number)
    positions instead of ScheduledLesson at calendar dates.

    The grid is bounded by course.duration_weeks × course.frequency_days.
    Days of week from each CourseSubjectConfig are mapped to day_number slots
    within each week (1-indexed), cycling through the available day slots.

    Args:
        course: A Course instance with duration_weeks and frequency_days set.
        subject_configs: Optional list of CourseSubjectConfig instances.
            If None, all active subject_configs for the course are used.

    Returns:
        The total number of PlanItem records created.
    """
    if subject_configs is None:
        subject_configs = list(
            course.subject_configs.filter(is_active=True).order_by("subject_name", "pk")
        )
    else:
        subject_configs = sorted(subject_configs, key=lambda cfg: (cfg.subject_name, cfg.pk))

    if not subject_configs:
        return 0

    duration_weeks = max(course.duration_weeks, 1)
    frequency_days = max(course.frequency_days, 1)

    # STEP 1: Build lesson queues per subject config
    queues = {}
    existing_pairs = set(
        LessonPlanDetail.objects.filter(
            plan_item__course=course,
            plan_item__item_type=PlanItem.ITEM_TYPE_LESSON,
            plan_item__is_active=True,
        ).values_list("course_subject_id", "curriculum_lesson_id")
    )

    for sc in subject_configs:
        lesson_subject = (sc.source_subject_name or "").strip() or sc.subject_name
        lesson_year = sc.source_year or sc.year
        queues[sc.id] = list(
            Lesson.objects.filter(
                subject_name=lesson_subject,
                year=lesson_year,
            ).order_by("unit_slug", "lesson_number")
        )

    # STEP 2: Parse days-of-week per subject config, mapped to 1-based day_number.
    # The course has frequency_days days per week (day_number 1..frequency_days).
    # CourseSubjectConfig.days_of_week stores 0-based weekday ints (0=Mon..6=Sun).
    # We map these to day_number slots: sort the chosen days, assign slot 1, 2, ...
    # Only use slots that fall within [1..frequency_days].
    subject_day_slots = {}  # {sc.id: list of 1-based day_number ints}
    for sc in subject_configs:
        raw_days = _normalize_day_values(course, sc.days_of_week)
        # Keep only days that map to valid slots (0..frequency_days-1 → day_number 1..frequency_days)
        valid_slots = [d + 1 for d in raw_days if 1 <= d + 1 <= frequency_days]
        if not valid_slots:
            # Default to all available day slots
            valid_slots = list(range(1, frequency_days + 1))
        subject_day_slots[sc.id] = valid_slots

    # STEP 3: Compute slots-per-day-slot per subject (same divmod logic as generate_schedule)
    slots_per_day_slot = {}  # {sc.id: {day_number: n_slots}}
    for sc in subject_configs:
        day_slots = subject_day_slots[sc.id]
        lpw = _normalize_lessons_per_week(sc.lessons_per_week)
        base, extra = divmod(lpw, len(day_slots))
        sdict = {}
        for i, day_num in enumerate(day_slots):
            sdict[day_num] = base + (1 if i < extra else 0)
        slots_per_day_slot[sc.id] = sdict

    # STEP 4: Distribute lessons into (week_number, day_number) grid positions
    to_create_plan_items = []

    # Track weekly slot usage per subject; reset each new week
    week_day_counts = {sc.id: {} for sc in subject_configs}

    for week_number in range(1, duration_weeks + 1):
        # Reset weekly counters at the start of each week
        week_day_counts = {sc.id: {} for sc in subject_configs}

        for day_number in range(1, frequency_days + 1):
            order = 0
            for sc in subject_configs:
                allowed = slots_per_day_slot[sc.id].get(day_number, 0)
                used = week_day_counts[sc.id].get(day_number, 0)
                while used < allowed and queues[sc.id]:
                    lesson = queues[sc.id].pop(0)
                    if (sc.id, lesson.id) in existing_pairs:
                        continue
                    plan_item = PlanItem(
                        course=course,
                        item_type=PlanItem.ITEM_TYPE_LESSON,
                        week_number=week_number,
                        day_number=day_number,
                        name=lesson.lesson_title,
                        description="",
                        order=order,
                        is_active=True,
                    )
                    to_create_plan_items.append((plan_item, sc, lesson))
                    existing_pairs.add((sc.id, lesson.id))
                    used += 1
                    order += 1
                week_day_counts[sc.id][day_number] = used

    # STEP 5: Bulk insert PlanItems, then create detail rows
    with transaction.atomic():
        # Create PlanItems one by one (bulk_create doesn't return PKs reliably on all DBs)
        # For large grids use batch inserts with returned IDs
        created_count = 0
        batch = []
        for plan_item, sc, lesson in to_create_plan_items:
            plan_item.save()
            batch.append(
                LessonPlanDetail(
                    plan_item=plan_item,
                    course_subject=sc,
                    curriculum_lesson=lesson,
                )
            )
            created_count += 1

        LessonPlanDetail.objects.bulk_create(batch, batch_size=500)

    return created_count



def check_vacation_conflicts(child, plan_items, enrollment):
    """Return list of (plan_item, calendar_date) tuples that overlap a vacation.

    Calendar date is computed from enrollment.start_date + (week-1)*7 + (day-1).
    Only PlanItem-based items (week_number, day_number set) are checked.
    """
    if not plan_items or enrollment.start_date is None:
        return []

    vacations = list(Vacation.objects.filter(child=child))
    if not vacations:
        return []

    conflicts = []
    for pi in plan_items:
        act_date = enrollment.start_date + datetime.timedelta(
            days=(pi.week_number - 1) * 7 + (pi.day_number - 1)
        )
        for vac in vacations:
            if vac.start_date <= act_date <= vac.end_date:
                conflicts.append((pi, act_date, vac))
                break

    return conflicts
