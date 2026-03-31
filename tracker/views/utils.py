from accounts.models import ParentSettings
from planning.models import StudentAssignment
from scheduler.models import ScheduledLesson


def _get_or_create_settings(user):
    if user is None:
        return None
    settings, _ = ParentSettings.objects.get_or_create(user=user)
    return settings


def _safe_int(raw_value):
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return None


def _base_assignment_queryset_for_role(user, role):
    """Return active student assignments visible to the requesting user."""
    queryset = StudentAssignment.objects.filter(enrollment__status="active")
    if role == "student":
        child = getattr(user, "child_profile", None)
        if child is None:
            return StudentAssignment.objects.none()
        return queryset.filter(enrollment__child=child)

    if role in {"parent", "teacher"}:
        return queryset.filter(enrollment__course__parent=user)

    return StudentAssignment.objects.none()


def _base_lesson_queryset_for_role(user, role):
    """Return scheduled lessons visible to the requesting user role."""
    queryset = ScheduledLesson.objects.select_related(
        "child",
        "lesson",
        "enrolled_subject",
        "log",
    )

    if role == "student":
        child = getattr(user, "child_profile", None)
        if child is None:
            return ScheduledLesson.objects.none()
        return queryset.filter(child=child)

    if role == "parent":
        return queryset.filter(child__parent=user)

    if role == "teacher":
        return queryset.filter(
            child__course_enrollments__course__parent=user,
            child__course_enrollments__status="active",
        ).distinct()

    return ScheduledLesson.objects.none()


def _grid_calendar_date(enrollment, plan_item):
    if enrollment is None or plan_item is None or enrollment.start_date is None:
        return None
    import datetime

    return enrollment.start_date + datetime.timedelta(
        days=(plan_item.week_number - 1) * 7 + (plan_item.day_number - 1)
    )


def _hydrate_assignment_display(assignment):
    source_plan = getattr(assignment, "new_plan_item", None)
    if source_plan is not None:
        assignment.display_name = source_plan.name
        assignment.display_description = source_plan.description
        assignment.display_notes = source_plan.notes
        detail = getattr(source_plan, "assignment_detail", None)
        assignment.display_assignment_type = (
            detail.assignment_type if detail and detail.assignment_type else None
        )
        return assignment

    legacy_plan_item = getattr(assignment, "plan_item", None)
    legacy_template = getattr(legacy_plan_item, "template", None)
    if legacy_plan_item and legacy_template:
        assignment.display_name = legacy_template.name
        assignment.display_description = legacy_template.description
        assignment.display_notes = getattr(legacy_plan_item, "notes", "")
        assignment.display_assignment_type = getattr(
            legacy_template, "assignment_type", None
        )
    return assignment


def _hydrate_activity_display(progress):
    source_plan = getattr(progress, "new_plan_item", None)
    if source_plan is not None:
        progress.display_name = source_plan.name
        progress.display_description = source_plan.description
        progress.display_date = _grid_calendar_date(progress.enrollment, source_plan)
        return progress

    legacy_plan_item = getattr(progress, "plan_item", None)
    legacy_template = getattr(legacy_plan_item, "template", None)
    if legacy_plan_item and legacy_template:
        progress.display_name = legacy_template.name
        progress.display_description = legacy_template.description
        progress.display_date = _grid_calendar_date(
            progress.enrollment, legacy_plan_item
        )
    return progress
