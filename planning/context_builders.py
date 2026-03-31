"""Context builders for planning views.

Extracted from plan_course_view to keep the view thin and the context
logic testable.
"""

from types import SimpleNamespace

from django.shortcuts import get_object_or_404
from django.utils import timezone

from courses.models import AssignmentType, sync_course_assignment_types_from_global
from scheduler.models import EnrolledSubject

from . import services as planning_services
from .models import (
    ActivityProgress,
    PlanItem,
    StudentAssignment,
)

WORKFLOW_ASSIGNMENTS = "assignments"
WORKFLOW_LESSONS = "lessons"
WORKFLOW_ACTIVITIES = "activities"

WORKFLOW_TO_ITEM_KIND = {
    WORKFLOW_ASSIGNMENTS: "assignment",
    WORKFLOW_LESSONS: "lesson",
    WORKFLOW_ACTIVITIES: "activity",
}
ITEM_KIND_TO_WORKFLOW = {
    item_kind: workflow for workflow, item_kind in WORKFLOW_TO_ITEM_KIND.items()
}


def safe_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_scope(raw_scope):
    return raw_scope if raw_scope in {"day", "all"} else "day"


def normalize_workflow(raw_workflow):
    return (
        raw_workflow if raw_workflow in WORKFLOW_TO_ITEM_KIND else WORKFLOW_ASSIGNMENTS
    )


def course_weeks(course):
    return list(range(1, max(course.duration_weeks, 1) + 1))


def course_days(course):
    return list(range(1, max(course.frequency_days, 1) + 1))


def build_plan_url(path, week, day, workflow, scope, create=False, edit_id=None):
    query = [f"week={week}", f"day={day}", f"workflow={workflow}", f"scope={scope}"]
    if create:
        query.append("create=1")
    if edit_id:
        query.append(f"edit={edit_id}")
    return f"{path}?{'&'.join(query)}"


def activity_status_from_rows(rows):
    statuses = {row.status for row in rows}
    if statuses and statuses == {"complete"}:
        return "complete"
    if statuses:
        return "pending"
    return None


def lesson_provenance(plan_item):
    enrolled_subject = plan_item.lesson_enrolled_subject
    scheduled_lesson = plan_item.scheduled_lesson
    lesson = getattr(scheduled_lesson, "lesson", None)
    if enrolled_subject and (
        (enrolled_subject.source_year or "").strip()
        or (enrolled_subject.source_subject_name or "").strip()
    ):
        return {"label": "Imported", "css": "imported"}
    if lesson and lesson.is_custom:
        return {"label": "Manual", "css": "manual"}
    if lesson:
        return {"label": "Oak", "css": "oak"}
    return None


def lesson_provenance_for_new(plan_item):
    detail = getattr(plan_item, "lesson_detail", None)
    if detail is None:
        return None
    course_subject = detail.course_subject
    lesson = detail.curriculum_lesson
    if course_subject and (
        (course_subject.source_year or "").strip()
        or (course_subject.source_subject_name or "").strip()
    ):
        return {"label": "Imported", "css": "imported"}
    if lesson and lesson.is_custom:
        return {"label": "Manual", "css": "manual"}
    if lesson:
        return {"label": "Oak", "css": "oak"}
    return None


def _display_id_for_legacy(item):
    legacy_id = item.id if hasattr(item, "id") else item
    return f"legacy-{legacy_id}"


def _display_id_for_new(plan_item):
    new_id = plan_item.id if hasattr(plan_item, "id") else plan_item
    return f"new-{new_id}"


def _serialize_new_plan_item(plan_item):
    return _serialize_canonical_plan_item(plan_item)


def _serialize_canonical_plan_item(plan_item, bridge_item=None):
    assignment_detail = getattr(plan_item, "assignment_detail", None)
    activity_detail = getattr(plan_item, "activity_detail", None)
    lesson_detail = getattr(plan_item, "lesson_detail", None)

    if plan_item.item_type == PlanItem.ITEM_TYPE_ASSIGNMENT:
        item_kind = "assignment"
        assignment_type = getattr(assignment_detail, "assignment_type", None)
        due_in_days = getattr(assignment_detail, "due_offset_days", 0)
        is_graded = getattr(assignment_detail, "is_graded", False)
    elif plan_item.item_type == PlanItem.ITEM_TYPE_ACTIVITY:
        item_kind = "activity"
        assignment_type = None
        due_in_days = getattr(activity_detail, "due_offset_days", 0)
        is_graded = False
    else:
        item_kind = "lesson"
        assignment_type = None
        due_in_days = 0
        is_graded = False

    lesson_subject = None
    scheduled_lesson = bridge_item.scheduled_lesson if bridge_item else None
    lesson_child = bridge_item.lesson_child if bridge_item else None
    notes = plan_item.notes
    if lesson_detail and lesson_detail.course_subject:
        lesson_subject = SimpleNamespace(
            subject_name=lesson_detail.course_subject.subject_name,
            source_year=lesson_detail.course_subject.source_year,
        )
    if scheduled_lesson is None and lesson_detail and lesson_detail.curriculum_lesson:
        scheduled_lesson = SimpleNamespace(lesson=lesson_detail.curriculum_lesson)

    return SimpleNamespace(
        id=_display_id_for_new(plan_item),
        plan_item_id=plan_item.id,
        display_id=_display_id_for_new(plan_item),
        legacy_id=bridge_item.id if bridge_item else None,
        new_plan_item=plan_item,
        week_number=plan_item.week_number,
        day_number=plan_item.day_number,
        order=plan_item.order,
        due_in_days=due_in_days,
        notes=notes,
        lesson_child=lesson_child,
        lesson_enrolled_subject=lesson_subject,
        scheduled_lesson=scheduled_lesson,
        template=SimpleNamespace(
            name=plan_item.name,
            description=plan_item.description,
            item_kind=item_kind,
            assignment_type=assignment_type,
            is_graded=is_graded,
        ),
    )


def _workflow_for_item(item):
    return ITEM_KIND_TO_WORKFLOW.get(item.template.item_kind, WORKFLOW_ASSIGNMENTS)


def _legacy_signature(item):
    return (
        item.template.item_kind,
        item.week_number,
        item.day_number,
        item.order,
        (item.template.name or "").strip().lower(),
    )


def _new_signature(plan_item):
    item_kind = {
        PlanItem.ITEM_TYPE_ASSIGNMENT: "assignment",
        PlanItem.ITEM_TYPE_LESSON: "lesson",
        PlanItem.ITEM_TYPE_ACTIVITY: "activity",
    }[plan_item.item_type]
    return (
        item_kind,
        plan_item.week_number,
        plan_item.day_number,
        plan_item.order,
        (plan_item.name or "").strip().lower(),
    )


def build_plan_course_context(course, request_params, active_enrollments):
    """Build the full template context dict for plan_course_view GET.

    Args:
        course: The Course instance.
        request_params: A dict-like object (request.GET) with query parameters.
        active_enrollments: List of active CourseEnrollment instances.

    Returns:
        A dict suitable for passing to render().
    """
    sync_course_assignment_types_from_global(course)

    weeks = course_weeks(course)
    days = course_days(course)

    assignment_types = AssignmentType.objects.filter(
        course=course, is_hidden=False
    ).order_by("order", "name")

    selected_week = safe_int(request_params.get("week", 1), 1) if weeks else 1
    selected_day = safe_int(request_params.get("day", 1), 1) if days else 1
    if selected_week not in weeks:
        selected_week = weeks[0] if weeks else 1
    if selected_day not in days:
        selected_day = days[0] if days else 1

    workflow = normalize_workflow(request_params.get("workflow", WORKFLOW_ASSIGNMENTS))
    scope = normalize_scope(request_params.get("scope", "day"))

    new_plan_items = list(
        PlanItem.objects.filter(course=course, is_active=True)
        .select_related(
            "lesson_detail__course_subject",
            "lesson_detail__curriculum_lesson",
            "assignment_detail__assignment_type",
            "activity_detail__course_subject",
        )
        .order_by("week_number", "day_number", "order", "id")
    )
    merged_plan_items = [
        _serialize_canonical_plan_item(plan_item, None) for plan_item in new_plan_items
    ]

    # Editing state
    edit_id = safe_int(request_params.get("edit"), None)
    create_mode = request_params.get("create") == "1" or bool(edit_id)
    editing_item = None
    editing_attachments = []
    student_assignments = []
    activity_progress_items = []

    if edit_id:
        editing_item = get_object_or_404(PlanItem, pk=edit_id, course=course)
        selected_week = editing_item.week_number
        selected_day = editing_item.day_number
        workflow = {
            PlanItem.ITEM_TYPE_ASSIGNMENT: WORKFLOW_ASSIGNMENTS,
            PlanItem.ITEM_TYPE_LESSON: WORKFLOW_LESSONS,
            PlanItem.ITEM_TYPE_ACTIVITY: WORKFLOW_ACTIVITIES,
        }.get(editing_item.item_type, workflow)
        editing_attachments = []
        editing_item = _serialize_canonical_plan_item(editing_item, None)
        student_assignments = list(
            StudentAssignment.objects.filter(
                new_plan_item_id=editing_item.plan_item_id
            ).select_related("enrollment__child")
        )
        activity_progress_items = list(
            ActivityProgress.objects.filter(new_plan_item_id=editing_item.plan_item_id)
            .select_related("enrollment__child")
            .prefetch_related("attachments")
        )

    # Build enrollment rows
    student_assignment_by_enrollment = {
        sa.enrollment_id: sa for sa in student_assignments
    }
    activity_progress_by_enrollment = {
        ap.enrollment_id: ap for ap in activity_progress_items
    }

    enrollment_rows = []
    activity_rows = []
    for enrollment in active_enrollments:
        sa = student_assignment_by_enrollment.get(enrollment.id)
        ap = activity_progress_by_enrollment.get(enrollment.id)
        enrollment_rows.append(
            {
                "enrollment": enrollment,
                "student_assignment": sa,
                "assigned": bool(sa) or not editing_item,
            }
        )
        activity_rows.append(
            {
                "enrollment": enrollment,
                "progress": ap,
                "assigned": bool(ap),
                "attachments": list(ap.attachments.all()) if ap else [],
            }
        )

    # Lesson options
    lesson_child_options = []
    for enrollment in active_enrollments:
        child = enrollment.child
        if any(opt["id"] == child.id for opt in lesson_child_options):
            continue
        lesson_child_options.append({"id": child.id, "name": child.first_name})

    lesson_subject_options = list(
        EnrolledSubject.objects.filter(
            child_id__in=[opt["id"] for opt in lesson_child_options],
            is_active=True,
        )
        .order_by("child__first_name", "subject_name")
        .values("id", "child_id", "subject_name", "source_year")
    )

    # Workflow counts and filtering
    workflow_counts = {
        WORKFLOW_ASSIGNMENTS: sum(
            1
            for item in merged_plan_items
            if _workflow_for_item(item) == WORKFLOW_ASSIGNMENTS
        ),
        WORKFLOW_LESSONS: sum(
            1
            for item in merged_plan_items
            if _workflow_for_item(item) == WORKFLOW_LESSONS
        ),
        WORKFLOW_ACTIVITIES: sum(
            1
            for item in merged_plan_items
            if _workflow_for_item(item) == WORKFLOW_ACTIVITIES
        ),
    }

    workflow_items = [
        item for item in merged_plan_items if _workflow_for_item(item) == workflow
    ]
    day_items = [
        item
        for item in workflow_items
        if item.week_number == selected_week and item.day_number == selected_day
    ]
    filtered_items = workflow_items if scope == "all" else day_items

    # Status maps
    plan_status_map = _build_plan_status_map([], new_plan_items)
    lesson_provenance_map = _build_lesson_provenance_map([], new_plan_items)
    vacation_conflicts = []
    for enrollment in active_enrollments:
        conflicts = planning_services.check_vacation_conflicts(
            enrollment.child, new_plan_items, enrollment
        )
        for plan_item, calendar_date, vacation in conflicts:
            vacation_conflicts.append(
                {
                    "display_id": _display_id_for_new(plan_item),
                    "plan_item_name": plan_item.name,
                    "child_name": enrollment.child.first_name,
                    "date": calendar_date,
                    "vacation_name": vacation.name,
                }
            )

    workflow_tabs = [
        {
            "key": WORKFLOW_ASSIGNMENTS,
            "label": "Assignments",
            "count": workflow_counts[WORKFLOW_ASSIGNMENTS],
        },
        {
            "key": WORKFLOW_LESSONS,
            "label": "Lessons",
            "count": workflow_counts[WORKFLOW_LESSONS],
        },
        {
            "key": WORKFLOW_ACTIVITIES,
            "label": "Activities",
            "count": workflow_counts[WORKFLOW_ACTIVITIES],
        },
    ]

    return {
        "course": course,
        "weeks": weeks,
        "days": days,
        "assignment_types": assignment_types,
        "plan_items": filtered_items,
        "day_items": day_items,
        "selected_week": selected_week,
        "selected_day": selected_day,
        "scope": scope,
        "scope_day_count": len(day_items),
        "scope_all_count": len(workflow_items),
        "workflow": workflow,
        "workflow_tabs": workflow_tabs,
        "create_mode": create_mode,
        "editing_item": editing_item,
        "editing_attachments": editing_attachments,
        "student_assignments": student_assignments,
        "active_enrollments": active_enrollments,
        "enrollment_rows": enrollment_rows,
        "activity_rows": activity_rows,
        "plan_status_map": plan_status_map,
        "lesson_provenance_map": lesson_provenance_map,
        "vacation_conflicts": vacation_conflicts,
        "item_kind_choices": [
            ("assignment", "Assignment"),
            ("activity", "Activity"),
            ("lesson", "Lesson"),
        ],
        "lesson_child_options": lesson_child_options,
        "lesson_subject_options": lesson_subject_options,
    }


def _status_from_assignment_values(values_rows, today):
    plan_status_map = {}
    for row in values_rows:
        status = row["status"]
        if status != "complete" and row["due_date"] < today:
            status = "overdue"
        plan_status_map.setdefault(row["key"], set()).add(status)

    collapsed = {}
    for key, statuses in plan_status_map.items():
        if "overdue" in statuses:
            collapsed[key] = "overdue"
        elif statuses == {"complete"}:
            collapsed[key] = "complete"
        else:
            collapsed[key] = "pending"
    return collapsed


def _build_plan_status_map(legacy_plan_items, new_plan_items):
    """Build a dict mapping display ids -> aggregate status string."""
    plan_status_map = {}
    today = timezone.localdate()

    new_ids = [item.id for item in new_plan_items]
    new_assignment_rows = [
        {
            "key": _display_id_for_new(row["new_plan_item_id"]),
            "status": row["status"],
            "due_date": row["due_date"],
        }
        for row in StudentAssignment.objects.filter(
            new_plan_item_id__in=new_ids
        ).values("new_plan_item_id", "status", "due_date")
        if row["new_plan_item_id"]
    ]
    plan_status_map.update(_status_from_assignment_values(new_assignment_rows, today))

    activity_status_rows = {}
    for progress in ActivityProgress.objects.filter(
        new_plan_item_id__in=new_ids
    ).select_related("enrollment__child"):
        if progress.new_plan_item_id:
            activity_status_rows.setdefault(
                _display_id_for_new(progress.new_plan_item_id), []
            ).append(progress)

    for display_id, rows in activity_status_rows.items():
        derived_status = activity_status_from_rows(rows)
        if derived_status:
            plan_status_map[display_id] = derived_status

    return plan_status_map


def _build_lesson_provenance_map(legacy_plan_items, new_plan_items):
    """Build a dict mapping display ids -> provenance dict."""
    provenance_map = {}
    for plan_item in new_plan_items:
        prov = lesson_provenance_for_new(plan_item)
        if prov:
            provenance_map[_display_id_for_new(plan_item)] = prov
    return provenance_map
