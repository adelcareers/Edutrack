"""Sequential student onboarding views."""

import datetime
import json

from django.contrib import messages
from django.contrib.auth.models import User
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from accounts.decorators import role_required
from accounts.forms import StudentCreationForm
from accounts.models import UserProfile
from courses.models import CourseSubjectConfig, CourseSubjectScheduleSlot
from curriculum.models import Lesson
from planning import services as planning_services
from scheduler.models import Child
from scheduler.onboarding import (
    DEFAULT_WORKSPACE_DAYS,
    clear_generated_lesson_data,
    clear_subject_timetable_data,
    ensure_student_workspace,
    get_student_workspace,
    mark_setup_complete,
    save_subject_selection,
    sync_legacy_birth_fields,
)


WEEKDAY_CHOICES = [
    (0, "Mon"),
    (1, "Tue"),
    (2, "Wed"),
    (3, "Thu"),
    (4, "Fri"),
    (5, "Sat"),
    (6, "Sun"),
]

SUBJECT_COLOUR_PALETTE = [
    "#E63946",
    "#2A9D8F",
    "#E9C46A",
    "#F4A261",
    "#264653",
    "#8338EC",
    "#3A86FF",
    "#FB5607",
    "#FFBE0B",
    "#06D6A0",
]


def _sorted_years():
    raw_years = Lesson.objects.values_list("year", flat=True).distinct()
    return sorted(
        set(raw_years),
        key=lambda y: int(y.split()[-1]) if y.split()[-1].isdigit() else 99,
    )


def _default_academic_start():
    today = timezone.localdate()
    year = today.year if today.month >= 9 else today.year - 1
    return datetime.date(year, 9, 1)


def _subject_rows_for_year(school_year):
    if not school_year:
        return []
    rows = list(
        Lesson.objects.filter(year=school_year, is_custom=False)
        .values("key_stage", "subject_name")
        .annotate(
            total_lessons=Count("id"),
            total_units=Count("unit_slug", distinct=True),
        )
        .order_by("key_stage", "subject_name")
    )
    for index, row in enumerate(rows):
        row["preview_colour"] = SUBJECT_COLOUR_PALETTE[
            index % len(SUBJECT_COLOUR_PALETTE)
        ]
    return rows


def _selected_subjects(workspace):
    if workspace is None:
        return []
    return list(workspace.subject_configs.filter(is_active=True).order_by("subject_name"))


def _slot_payload(workspace):
    if workspace is None:
        return []
    slots = (
        CourseSubjectScheduleSlot.objects.filter(course_subject__course=workspace)
        .select_related("course_subject")
        .order_by("weekday", "period", "course_subject__subject_name")
    )
    return [
        {
            "subject_name": slot.course_subject.subject_name,
            "weekday": slot.weekday,
            "period": slot.period,
            "colour_hex": slot.course_subject.colour_hex,
        }
        for slot in slots
    ]


def _current_generation_summary(request, child):
    key = f"onboarding_summary_{child.id}"
    summary = request.session.pop(key, None)
    if not summary:
        return []
    return summary


def _save_generation_summary(request, child, summary):
    request.session[f"onboarding_summary_{child.id}"] = summary
    request.session.modified = True


def _section_completion(child, workspace):
    selected_subjects = _selected_subjects(workspace)
    slots = _slot_payload(workspace)
    return {
        "info": bool(child and child.first_name and child.date_of_birth),
        "credentials": bool(child and child.student_user_id),
        "school_year": bool(child and child.school_year and workspace),
        "subjects": bool(selected_subjects),
        "timetable": bool(slots),
        "generated": bool(child and child.is_setup_complete),
    }


def _next_open_section(completion):
    for key in ("info", "credentials", "school_year", "subjects", "timetable"):
        if not completion[key]:
            return key
    return "generated" if completion["generated"] else "timetable"


def _upsert_student_user(child, form):
    email = form.cleaned_data["email"].lower().strip()
    password = form.cleaned_data["password1"]
    if child.student_user_id:
        user = child.student_user
        user.username = email
        user.email = email
        user.set_password(password)
        user.save(update_fields=["username", "email", "password"])
        return user
    user = User.objects.create_user(
        username=email,
        email=email,
        password=password,
    )
    UserProfile.objects.create(user=user, role="student")
    child.student_user = user
    child.save(update_fields=["student_user"])
    return user


def _parse_slots(raw_value, valid_subject_names):
    try:
        parsed = json.loads(raw_value or "[]")
    except json.JSONDecodeError:
        return None, "Timetable data could not be parsed."
    if not isinstance(parsed, list):
        return None, "Timetable data is invalid."

    normalized = []
    occupied = set()
    per_subject_counts = {}
    for row in parsed:
        if not isinstance(row, dict):
            return None, "Timetable data is invalid."
        subject_name = (row.get("subject_name") or "").strip()
        if subject_name not in valid_subject_names:
            return None, "Timetable includes an unknown subject."
        try:
            weekday = int(row.get("weekday"))
            period = int(row.get("period"))
        except (TypeError, ValueError):
            return None, "Timetable includes an invalid day or period."
        if weekday < 0 or weekday > 6 or period < 0 or period > 12:
            return None, "Timetable slots must stay within Mon-Sun and periods 0-12."
        if (weekday, period) in occupied:
            return None, "Only one subject can occupy each timetable slot."
        occupied.add((weekday, period))
        per_subject_counts[subject_name] = per_subject_counts.get(subject_name, 0) + 1
        if per_subject_counts[subject_name] > 10:
            return (
                None,
                f"{subject_name} cannot exceed 10 lessons per week in this MVP.",
            )
        normalized.append(
            {
                "subject_name": subject_name,
                "weekday": weekday,
                "period": period,
            }
        )

    missing = [name for name in valid_subject_names if per_subject_counts.get(name, 0) < 1]
    if missing:
        return None, f"Add at least one timetable slot for {missing[0]}."
    normalized.sort(key=lambda row: (row["weekday"], row["period"], row["subject_name"]))
    return normalized, None


def _build_context(request, child):
    workspace = get_student_workspace(child) if child else None
    completion = _section_completion(child, workspace) if child else {
        "info": False,
        "credentials": False,
        "school_year": False,
        "subjects": False,
        "timetable": False,
        "generated": False,
    }
    subject_rows = _subject_rows_for_year(child.school_year if child else "")
    selected_subjects = _selected_subjects(workspace)
    selected_names = {subject.subject_name for subject in selected_subjects}
    selected_colours = {
        subject.subject_name: subject.colour_hex for subject in selected_subjects
    }
    for row in subject_rows:
        row["current_colour"] = selected_colours.get(
            row["subject_name"], row["preview_colour"]
        )
    credentials_form = StudentCreationForm(
        initial={
            "email": (
                child.student_user.email or child.student_user.username
                if child and child.student_user_id
                else ""
            )
        }
    )
    slot_payload = _slot_payload(workspace)
    slot_subjects = [
        {
            "subject_name": subject.subject_name,
            "colour_hex": subject.colour_hex,
            "slot_count": len(
                [slot for slot in slot_payload if slot["subject_name"] == subject.subject_name]
            ),
        }
        for subject in selected_subjects
    ]
    return {
        "child": child,
        "workspace": workspace,
        "completion": completion,
        "open_section": _next_open_section(completion),
        "school_years": _sorted_years(),
        "subject_rows": subject_rows,
        "selected_names": selected_names,
        "selected_colours": selected_colours,
        "credentials_form": credentials_form,
        "selected_subjects": selected_subjects,
        "weekday_choices": WEEKDAY_CHOICES,
        "period_choices": list(range(13)),
        "slot_subjects": slot_subjects,
        "slot_payload_json": json.dumps(slot_payload),
        "generation_summary": _current_generation_summary(request, child) if child else [],
    }


def _render_page(request, child, extra_context=None):
    context = _build_context(request, child)
    if extra_context:
        context.update(extra_context)
    return render(request, "scheduler/student_onboarding.html", context)


@role_required("parent")
def student_onboarding_new_view(request):
    if request.method == "POST":
        return _handle_onboarding_post(request, None)
    return _render_page(request, None)


@role_required("parent")
def student_onboarding_resume_view(request, child_id):
    child = get_object_or_404(Child, pk=child_id, parent=request.user)
    if request.method == "POST":
        return _handle_onboarding_post(request, child)
    return _render_page(request, child)


def _handle_onboarding_post(request, child):
    action = (request.POST.get("action") or "").strip()
    if action == "save_info":
        first_name = (request.POST.get("first_name") or "").strip()
        date_of_birth_raw = (request.POST.get("date_of_birth") or "").strip()
        errors = {}
        if not first_name:
            errors["first_name"] = "Student name is required."
        try:
            date_of_birth = (
                datetime.date.fromisoformat(date_of_birth_raw)
                if date_of_birth_raw
                else None
            )
        except ValueError:
            date_of_birth = None
            errors["date_of_birth"] = "Enter a valid date of birth."
        if date_of_birth is None and "date_of_birth" not in errors:
            errors["date_of_birth"] = "Date of birth is required."
        if errors:
            draft_child = child
            return _render_page(
                request,
                draft_child,
                {
                    "info_errors": errors,
                    "info_form_data": {
                        "first_name": first_name,
                        "date_of_birth": date_of_birth_raw,
                    },
                    "open_section": "info",
                },
            )
        if child is None:
            child = Child(
                parent=request.user,
                academic_year_start=_default_academic_start(),
                school_year="",
                is_setup_complete=False,
            )
        child.first_name = first_name
        child.date_of_birth = date_of_birth
        sync_legacy_birth_fields(child)
        if request.FILES.get("photo"):
            child.photo = request.FILES["photo"]
        child.save()
        workspace = get_student_workspace(child)
        if workspace is not None:
            ensure_student_workspace(child)
        messages.success(request, "Student information saved.")
        return redirect("scheduler:student_onboarding_resume", child_id=child.pk)

    if child is None:
        messages.error(request, "Save the student information section first.")
        return redirect("scheduler:student_onboarding_new")

    if action == "save_credentials":
        form = StudentCreationForm(request.POST)
        if not form.is_valid():
            return _render_page(
                request,
                child,
                {
                    "credentials_form": form,
                    "open_section": "credentials",
                },
            )
        _upsert_student_user(child, form)
        messages.success(request, "Student login details saved.")
        return redirect("scheduler:student_onboarding_resume", child_id=child.pk)

    if action == "save_school_year":
        school_year = (request.POST.get("school_year") or "").strip()
        if not school_year:
            return _render_page(
                request,
                child,
                {
                    "school_year_error": "School year is required.",
                    "open_section": "school_year",
                },
            )
        changed = child.school_year != school_year
        child.school_year = school_year
        child.save(update_fields=["school_year"])
        workspace, _ = ensure_student_workspace(child)
        if changed:
            clear_subject_timetable_data(child, workspace)
            mark_setup_complete(child, False)
            messages.info(
                request,
                "School year updated. Subject, timetable, and generated lesson data were cleared.",
            )
        else:
            messages.success(request, "School year saved.")
        return redirect("scheduler:student_onboarding_resume", child_id=child.pk)

    workspace = get_student_workspace(child)
    if workspace is None:
        messages.error(request, "Save the school year section first.")
        return redirect("scheduler:student_onboarding_resume", child_id=child.pk)

    if action == "save_subjects":
        subject_rows = _subject_rows_for_year(child.school_year)
        stats_by_name = {row["subject_name"]: row for row in subject_rows}
        selected_names = []
        for name in request.POST.getlist("subjects"):
            cleaned = name.strip()
            if cleaned and cleaned in stats_by_name and cleaned not in selected_names:
                selected_names.append(cleaned)
        if len(selected_names) < 1 or len(selected_names) > 28:
            return _render_page(
                request,
                child,
                {
                    "subjects_error": "Select between 1 and 28 subjects.",
                    "open_section": "subjects",
                },
            )
        existing_names = set(
            workspace.subject_configs.filter(is_active=True).values_list(
                "subject_name", flat=True
            )
        )
        selected_subjects = []
        for subject_name in selected_names:
            stats = stats_by_name[subject_name]
            colour_hex = (
                request.POST.get(f"colour_{subject_name}") or stats["preview_colour"]
            )
            selected_subjects.append(
                {
                    "subject_name": subject_name,
                    "key_stage": stats["key_stage"],
                    "year": child.school_year,
                    "colour_hex": colour_hex,
                    "lessons_per_week": (
                        workspace.subject_configs.filter(subject_name=subject_name)
                        .values_list("lessons_per_week", flat=True)
                        .first()
                        or 1
                    ),
                    "days_of_week": (
                        workspace.subject_configs.filter(subject_name=subject_name)
                        .values_list("days_of_week", flat=True)
                        .first()
                        or list(DEFAULT_WORKSPACE_DAYS)
                    ),
                    "source": "oak",
                    "source_subject_name": subject_name,
                    "source_year": child.school_year,
                }
            )
        if set(selected_names) != existing_names:
            clear_generated_lesson_data(child, workspace)
            CourseSubjectScheduleSlot.objects.filter(course_subject__course=workspace).delete()
            mark_setup_complete(child, False)
            messages.info(
                request,
                "Subject choices changed. Timetable and generated lessons were cleared.",
            )
        save_subject_selection(child, workspace, selected_subjects)
        if set(selected_names) == existing_names:
            messages.success(request, "Subjects saved.")
        return redirect("scheduler:student_onboarding_resume", child_id=child.pk)

    if action == "save_timetable":
        selected_subjects = list(
            workspace.subject_configs.filter(is_active=True).order_by("subject_name")
        )
        valid_subject_names = [subject.subject_name for subject in selected_subjects]
        if not valid_subject_names:
            messages.error(request, "Select subjects before saving the timetable.")
            return redirect("scheduler:student_onboarding_resume", child_id=child.pk)
        slots, error = _parse_slots(request.POST.get("slots_json"), valid_subject_names)
        if error:
            return _render_page(
                request,
                child,
                {
                    "timetable_error": error,
                    "open_section": "timetable",
                    "slot_payload_json": request.POST.get("slots_json") or "[]",
                },
            )
        clear_generated_lesson_data(child, workspace)
        CourseSubjectScheduleSlot.objects.filter(course_subject__course=workspace).delete()
        config_map = {subject.subject_name: subject for subject in selected_subjects}
        counts = {name: 0 for name in valid_subject_names}
        weekdays = {name: set() for name in valid_subject_names}
        to_create = []
        for row in slots:
            config = config_map[row["subject_name"]]
            counts[config.subject_name] += 1
            weekdays[config.subject_name].add(row["weekday"])
            to_create.append(
                CourseSubjectScheduleSlot(
                    course_subject=config,
                    weekday=row["weekday"],
                    period=row["period"],
                )
            )
        CourseSubjectScheduleSlot.objects.bulk_create(to_create)
        for subject_name, config in config_map.items():
            days_of_week = sorted(weekdays[subject_name])
            lessons_per_week = counts[subject_name]
            config.lessons_per_week = lessons_per_week
            config.days_of_week = days_of_week
            config.save(update_fields=["lessons_per_week", "days_of_week"])
            enrolled = child.enrolled_subjects.filter(subject_name=subject_name).first()
            if enrolled is not None:
                enrolled.lessons_per_week = lessons_per_week
                enrolled.days_of_week = days_of_week
                enrolled.save(update_fields=["lessons_per_week", "days_of_week"])
        mark_setup_complete(child, False)
        messages.success(request, "Timetable draft saved.")
        return redirect("scheduler:student_onboarding_resume", child_id=child.pk)

    if action == "generate_lessons":
        enrollment = workspace.enrollments.filter(child=child, status="active").first()
        if enrollment is None:
            messages.error(request, "No active workspace enrollment exists for this student.")
            return redirect("scheduler:student_onboarding_resume", child_id=child.pk)
        summary = planning_services.generate_lessons_from_timetable(workspace, enrollment)
        mark_setup_complete(child, True)
        _save_generation_summary(request, child, summary)
        messages.success(request, "Lesson cards generated and added to the runtime calendar.")
        return redirect("scheduler:student_onboarding_resume", child_id=child.pk)

    messages.error(request, "Unknown onboarding action.")
    return redirect("scheduler:student_onboarding_resume", child_id=child.pk)
