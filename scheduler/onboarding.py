"""Services for the student onboarding workflow."""

import datetime

from django.db import transaction
from django.utils import timezone

from courses.models import (
    LEGACY_GRADE_YEAR_KEY_MAP,
    Course,
    CourseEnrollment,
    CourseSubjectConfig,
    CourseSubjectScheduleSlot,
    Subject,
    sync_course_assignment_types_from_global,
)
from planning.models import LessonPlanDetail, PlanItem
from scheduler.models import EnrolledSubject, ScheduledLesson

WORKSPACE_DURATION_WEEKS = 40
WORKSPACE_FREQUENCY_DAYS = 7
DEFAULT_WORKSPACE_DAYS = [0, 1, 2, 3, 4]
DEFAULT_SUBJECT_COURSE_COLOR = "#6c757d"


def sync_legacy_birth_fields(child):
    """Keep legacy birth_month/year populated when date_of_birth is present."""
    if child.date_of_birth is None:
        return child
    child.birth_month = child.date_of_birth.month
    child.birth_year = child.date_of_birth.year
    return child


def _normalized_grade_year_key(raw_value):
    value = (raw_value or "").strip()
    if not value:
        return ""
    lowered = value.lower()
    if lowered.startswith("year "):
        suffix = value.split()[-1]
        if suffix.isdigit():
            return suffix
    return LEGACY_GRADE_YEAR_KEY_MAP.get(lowered, value)


def _subject_course_name(child, subject_name):
    school_year = (child.school_year or "").strip()
    if school_year:
        return f"{school_year} - {subject_name}"
    return subject_name


def _repair_student_enrollment(enrollment):
    """Keep generated student-course enrollments aligned with actual join date."""
    today = timezone.localdate()
    updates = []
    if enrollment.start_date is None:
        enrollment.start_date = today
        updates.append("start_date")
    elif enrollment.enrolled_at is not None:
        enrolled_date = timezone.localtime(enrollment.enrolled_at).date()
        if (
            enrollment.start_date == enrollment.child.academic_year_start
            and enrolled_date
        ):
            if enrolled_date != enrollment.start_date:
                enrollment.start_date = enrolled_date
                updates.append("start_date")
    if enrollment.status != "active":
        enrollment.status = "active"
        enrollment.completed_school_year = ""
        enrollment.completed_calendar_year = None
        enrollment.completed_at = None
        updates.extend(
            [
                "status",
                "completed_school_year",
                "completed_calendar_year",
                "completed_at",
            ]
        )
    if updates:
        enrollment.save(update_fields=updates)
    return enrollment


def repair_student_course_enrollment(enrollment):
    """Public wrapper used by views before generating student-course lessons."""
    return _repair_student_enrollment(enrollment)


def get_student_workspace_courses(child):
    """Return all student-owned generated courses for a child."""
    if child is None:
        return Course.objects.none()
    return (
        Course.objects.filter(student_owner=child, is_student_workspace=True)
        .prefetch_related("subject_configs", "enrollments", "subjects")
        .order_by("name", "id")
    )


def get_student_workspace(child):
    """Backward-compatible alias returning the first student-owned course."""
    return get_student_workspace_courses(child).first()


def get_student_subject_course_map(child):
    """Return a mapping of subject_name -> generated student course."""
    mapping = {}
    for course in get_student_workspace_courses(child):
        configs = list(course.subject_configs.all())
        if not configs:
            continue
        subject_name = (configs[0].subject_name or "").strip()
        if subject_name and subject_name not in mapping:
            mapping[subject_name] = course
    return mapping


def get_student_workspace_course_for_subject(child, subject_name):
    return get_student_subject_course_map(child).get((subject_name or "").strip())


def ensure_student_workspace(child):
    """Backward-compatible alias returning first generated course + enrollment."""
    course = get_student_workspace(child)
    if course is None:
        return None, None
    enrollment = (
        CourseEnrollment.objects.filter(course=course, child=child, status="active")
        .order_by("id")
        .first()
    )
    if enrollment is not None:
        enrollment = _repair_student_enrollment(enrollment)
    return course, enrollment


def _delete_course_runtime(course):
    lesson_plan_items = list(
        PlanItem.objects.filter(
            course=course, item_type=PlanItem.ITEM_TYPE_LESSON
        ).values_list("id", flat=True)
    )
    if lesson_plan_items:
        ScheduledLesson.objects.filter(plan_item_id__in=lesson_plan_items).delete()
        LessonPlanDetail.objects.filter(plan_item_id__in=lesson_plan_items).delete()
        PlanItem.objects.filter(id__in=lesson_plan_items).delete()

    ScheduledLesson.objects.filter(course_subject__course=course).delete()


def _delete_subject_course(course):
    _delete_course_runtime(course)
    course.delete()


def clear_generated_lesson_data(child, course=None):
    """Clear lesson generation artifacts for one or all student subject courses."""
    courses = (
        [course] if course is not None else list(get_student_workspace_courses(child))
    )
    for current in courses:
        _delete_course_runtime(current)


def clear_subject_timetable_data(child, course=None):
    """Clear subject-course slots/configs/runtime, or remove all subject courses."""
    if course is not None:
        clear_generated_lesson_data(child, course)
        CourseSubjectScheduleSlot.objects.filter(course_subject__course=course).delete()
        CourseSubjectConfig.objects.filter(course=course).delete()
        return

    for current in list(get_student_workspace_courses(child)):
        _delete_subject_course(current)
    EnrolledSubject.objects.filter(child=child).delete()
    ScheduledLesson.objects.filter(child=child).delete()


def mark_setup_complete(child, complete=True):
    child.is_setup_complete = complete
    child.save(update_fields=["is_setup_complete", "onboarding_updated_at"])


def ensure_student_subject_course(child, payload):
    """Create or update one subject-specific generated course for a child."""
    today = timezone.localdate()
    if child.academic_year_start is None:
        academic_start_year = today.year if today.month >= 9 else today.year - 1
        child.academic_year_start = datetime.date(academic_start_year, 9, 1)
        child.save(update_fields=["academic_year_start"])

    subject_name = (payload.get("subject_name") or "").strip()
    colour_hex = payload.get("colour_hex") or DEFAULT_SUBJECT_COURSE_COLOR
    existing_course = get_student_workspace_course_for_subject(child, subject_name)

    course_defaults = {
        "name": _subject_course_name(child, subject_name),
        "color": colour_hex,
        "duration_weeks": WORKSPACE_DURATION_WEEKS,
        "frequency_days": WORKSPACE_FREQUENCY_DAYS,
        "default_days": list(DEFAULT_WORKSPACE_DAYS),
        "grade_years": _normalized_grade_year_key(child.school_year),
    }
    if existing_course is None:
        course = Course.objects.create(
            parent=child.parent,
            student_owner=child,
            is_student_workspace=True,
            **course_defaults,
        )
    else:
        course = existing_course
        updates = []
        for field, desired in course_defaults.items():
            current = getattr(course, field)
            if field == "default_days":
                if list(current or []) != list(desired):
                    setattr(course, field, desired)
                    updates.append(field)
                continue
            if current != desired:
                setattr(course, field, desired)
                updates.append(field)
        if not course.is_student_workspace:
            course.is_student_workspace = True
            updates.append("is_student_workspace")
        if course.student_owner_id != child.id:
            course.student_owner = child
            updates.append("student_owner")
        if updates:
            course.save(update_fields=updates)

    subject_obj, _ = Subject.objects.get_or_create(
        parent=child.parent,
        name=subject_name,
    )
    course.subjects.set([subject_obj])
    sync_course_assignment_types_from_global(course)

    enrollment, _ = CourseEnrollment.objects.get_or_create(
        course=course,
        child=child,
        status="active",
        defaults={
            "start_date": today,
            "days_of_week": list(payload.get("days_of_week") or DEFAULT_WORKSPACE_DAYS),
        },
    )
    enrollment = _repair_student_enrollment(enrollment)
    desired_enrollment_days = list(
        payload.get("days_of_week") or enrollment.days_of_week or DEFAULT_WORKSPACE_DAYS
    )
    if list(enrollment.days_of_week or []) != desired_enrollment_days:
        enrollment.days_of_week = desired_enrollment_days
        enrollment.save(update_fields=["days_of_week"])

    defaults = {
        "key_stage": payload.get("key_stage", ""),
        "year": payload.get("year", child.school_year),
        "lessons_per_week": payload.get("lessons_per_week", 1),
        "days_of_week": list(payload.get("days_of_week") or DEFAULT_WORKSPACE_DAYS),
        "colour_hex": colour_hex,
        "source": payload.get("source", "oak"),
        "source_subject_name": payload.get("source_subject_name", subject_name),
        "source_year": payload.get(
            "source_year", payload.get("year", child.school_year)
        ),
        "is_active": True,
    }
    config, _ = CourseSubjectConfig.objects.update_or_create(
        course=course,
        subject_name=subject_name,
        defaults=defaults,
    )
    CourseSubjectConfig.objects.filter(course=course).exclude(pk=config.pk).delete()
    return course, enrollment, config


@transaction.atomic
def save_subject_selection(child, selected_subjects):
    """Create/update/delete generated subject courses and legacy subject mirrors."""
    desired_names = []
    subject_map = {}
    for subject in selected_subjects:
        subject_name = (subject.get("subject_name") or "").strip()
        if not subject_name or subject_name in desired_names:
            continue
        desired_names.append(subject_name)
        subject_map[subject_name] = subject

    existing_course_map = get_student_subject_course_map(child)
    existing_names = set(existing_course_map.keys())
    desired_name_set = set(desired_names)
    selection_changed = bool(existing_names) and existing_names != desired_name_set

    if selection_changed:
        for course in existing_course_map.values():
            clear_generated_lesson_data(child, course)
            CourseSubjectScheduleSlot.objects.filter(
                course_subject__course=course
            ).delete()

    removed_names = existing_names - desired_name_set
    for subject_name in removed_names:
        _delete_subject_course(existing_course_map[subject_name])

    EnrolledSubject.objects.filter(child=child).exclude(
        subject_name__in=desired_names
    ).delete()

    courses = []
    configs = []
    legacy_subjects = []
    for subject_name in desired_names:
        payload = subject_map[subject_name]
        course, enrollment, config = ensure_student_subject_course(child, payload)
        courses.append(course)
        configs.append(config)
        legacy_subject, _ = EnrolledSubject.objects.update_or_create(
            child=child,
            subject_name=subject_name,
            defaults={
                "key_stage": payload.get("key_stage") or "Custom",
                "lessons_per_week": config.lessons_per_week,
                "colour_hex": config.colour_hex,
                "days_of_week": list(config.days_of_week or []),
                "source_year": config.source_year,
                "source_subject_name": config.source_subject_name,
                "is_active": True,
            },
        )
        if list(enrollment.days_of_week or []) != list(config.days_of_week or []):
            enrollment.days_of_week = list(config.days_of_week or [])
            enrollment.save(update_fields=["days_of_week"])
        legacy_subjects.append(legacy_subject)

    return courses, configs, legacy_subjects, selection_changed
