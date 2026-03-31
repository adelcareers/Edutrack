"""Services for the student onboarding workflow."""

import datetime

from django.db import transaction
from django.utils import timezone

from courses.models import Course, CourseEnrollment, CourseSubjectConfig, CourseSubjectScheduleSlot
from planning.models import LessonPlanDetail, PlanItem
from scheduler.models import EnrolledSubject, ScheduledLesson


WORKSPACE_DURATION_WEEKS = 40
WORKSPACE_FREQUENCY_DAYS = 7
DEFAULT_WORKSPACE_DAYS = [0, 1, 2, 3, 4]


def _workspace_name(child):
    base_name = child.first_name.strip() or f"Student {child.pk}"
    return f"{base_name} Workspace"


def sync_legacy_birth_fields(child):
    """Keep legacy birth_month/year populated when date_of_birth is present."""
    if child.date_of_birth is None:
        return child
    child.birth_month = child.date_of_birth.month
    child.birth_year = child.date_of_birth.year
    return child


def ensure_student_workspace(child):
    """Create or update the dedicated course and active enrollment for a child."""
    today = timezone.localdate()
    if child.academic_year_start is None:
        academic_start_year = today.year if today.month >= 9 else today.year - 1
        child.academic_year_start = datetime.date(academic_start_year, 9, 1)
        child.save(update_fields=["academic_year_start"])

    course, _ = Course.objects.get_or_create(
        parent=child.parent,
        student_owner=child,
        is_student_workspace=True,
        defaults={
            "name": _workspace_name(child),
            "color": "#6c757d",
            "duration_weeks": WORKSPACE_DURATION_WEEKS,
            "frequency_days": WORKSPACE_FREQUENCY_DAYS,
            "default_days": list(DEFAULT_WORKSPACE_DAYS),
        },
    )
    updates = []
    desired_name = _workspace_name(child)
    if course.name != desired_name:
        course.name = desired_name
        updates.append("name")
    if course.duration_weeks != WORKSPACE_DURATION_WEEKS:
        course.duration_weeks = WORKSPACE_DURATION_WEEKS
        updates.append("duration_weeks")
    if course.frequency_days != WORKSPACE_FREQUENCY_DAYS:
        course.frequency_days = WORKSPACE_FREQUENCY_DAYS
        updates.append("frequency_days")
    if list(course.default_days or []) != list(DEFAULT_WORKSPACE_DAYS):
        course.default_days = list(DEFAULT_WORKSPACE_DAYS)
        updates.append("default_days")
    if not course.is_student_workspace:
        course.is_student_workspace = True
        updates.append("is_student_workspace")
    if course.student_owner_id != child.id:
        course.student_owner = child
        updates.append("student_owner")
    if updates:
        course.save(update_fields=updates)

    enrollment, _ = CourseEnrollment.objects.get_or_create(
        course=course,
        child=child,
        status="active",
        defaults={
            "start_date": today,
            "days_of_week": list(DEFAULT_WORKSPACE_DAYS),
        },
    )
    enrollment_updates = []
    if enrollment.start_date is None:
        enrollment.start_date = today
        enrollment_updates.append("start_date")
    elif (
        course.is_student_workspace
        and enrollment.start_date == child.academic_year_start
        and enrollment.enrolled_at is not None
    ):
        enrolled_date = timezone.localtime(enrollment.enrolled_at).date()
        if enrolled_date != enrollment.start_date:
            enrollment.start_date = enrolled_date
            enrollment_updates.append("start_date")
    if list(enrollment.days_of_week or []) != list(DEFAULT_WORKSPACE_DAYS):
        enrollment.days_of_week = list(DEFAULT_WORKSPACE_DAYS)
        enrollment_updates.append("days_of_week")
    if enrollment.status != "active":
        enrollment.status = "active"
        enrollment.completed_school_year = ""
        enrollment.completed_calendar_year = None
        enrollment.completed_at = None
        enrollment_updates.extend(
            [
                "status",
                "completed_school_year",
                "completed_calendar_year",
                "completed_at",
            ]
        )
    if enrollment_updates:
        enrollment.save(update_fields=enrollment_updates)
    return course, enrollment


def get_student_workspace(child):
    return (
        Course.objects.filter(student_owner=child, is_student_workspace=True)
        .order_by("id")
        .first()
    )


def clear_generated_lesson_data(child, course=None):
    """Clear lesson generation artifacts for a child's workspace."""
    workspace = course or get_student_workspace(child)
    if workspace is None:
        return
    lesson_plan_items = list(
        PlanItem.objects.filter(
            course=workspace,
            item_type=PlanItem.ITEM_TYPE_LESSON,
        ).values_list("id", flat=True)
    )
    if lesson_plan_items:
        ScheduledLesson.objects.filter(plan_item_id__in=lesson_plan_items).delete()
        LessonPlanDetail.objects.filter(plan_item_id__in=lesson_plan_items).delete()
        PlanItem.objects.filter(id__in=lesson_plan_items).delete()


def clear_subject_timetable_data(child, course=None):
    """Clear subject configs, legacy subjects, slots, and generated lessons."""
    workspace = course or get_student_workspace(child)
    if workspace is None:
        EnrolledSubject.objects.filter(child=child).delete()
        ScheduledLesson.objects.filter(child=child).delete()
        return
    clear_generated_lesson_data(child, workspace)
    CourseSubjectScheduleSlot.objects.filter(course_subject__course=workspace).delete()
    CourseSubjectConfig.objects.filter(course=workspace).delete()
    EnrolledSubject.objects.filter(child=child).delete()
    ScheduledLesson.objects.filter(child=child, course_subject__course=workspace).delete()


def mark_setup_complete(child, complete=True):
    child.is_setup_complete = complete
    child.save(update_fields=["is_setup_complete", "onboarding_updated_at"])


@transaction.atomic
def save_subject_selection(child, course, selected_subjects):
    """Dual-write subject selection to CourseSubjectConfig and EnrolledSubject."""
    desired_names = []
    for subject in selected_subjects:
        name = (subject.get("subject_name") or "").strip()
        if name and name not in desired_names:
            desired_names.append(name)
    EnrolledSubject.objects.filter(child=child).exclude(
        subject_name__in=desired_names
    ).delete()
    CourseSubjectConfig.objects.filter(course=course).exclude(
        subject_name__in=desired_names
    ).delete()

    subject_map = {}
    for subject in selected_subjects:
        subject_name = (subject.get("subject_name") or "").strip()
        if not subject_name:
            continue
        subject_map[subject_name] = subject

    configs = []
    legacy_subjects = []
    for subject_name, payload in subject_map.items():
        defaults = {
            "key_stage": payload.get("key_stage", ""),
            "year": payload.get("year", child.school_year),
            "lessons_per_week": payload.get("lessons_per_week", 1),
            "days_of_week": payload.get("days_of_week", list(DEFAULT_WORKSPACE_DAYS)),
            "colour_hex": payload.get("colour_hex", "#6c757d"),
            "source": payload.get("source", "oak"),
            "source_subject_name": payload.get("source_subject_name", subject_name),
            "source_year": payload.get("source_year", payload.get("year", child.school_year)),
            "is_active": True,
        }
        config, _ = CourseSubjectConfig.objects.update_or_create(
            course=course,
            subject_name=subject_name,
            defaults=defaults,
        )
        legacy_subject, _ = EnrolledSubject.objects.update_or_create(
            child=child,
            subject_name=subject_name,
            defaults={
                "key_stage": defaults["key_stage"] or "Custom",
                "lessons_per_week": defaults["lessons_per_week"],
                "colour_hex": defaults["colour_hex"],
                "days_of_week": list(defaults["days_of_week"]),
                "source_year": defaults["source_year"],
                "source_subject_name": defaults["source_subject_name"],
                "is_active": True,
            },
        )
        configs.append(config)
        legacy_subjects.append(legacy_subject)
    return configs, legacy_subjects
