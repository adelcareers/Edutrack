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
