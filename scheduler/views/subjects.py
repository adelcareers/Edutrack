"""Subject selection + custom subjects views."""

import csv
import io
import json
import uuid

from django.contrib import messages
from django.db.models import Count
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import role_required
from courses.models import CourseSubjectConfig
from curriculum.models import Lesson
from scheduler.models import Child, CustomSubjectGroup, EnrolledSubject

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


def _build_subject_groups(child, user):
    """Return grouped subject data with preview colours for ``subject_selection_view``.

    Includes curriculum subjects for the child's school year plus any custom
    subjects created by the parent.  A palette colour is pre-assigned to every
    subject so the grid can show swatches before the form is submitted.

    Returns a dict:  {key_stage: [{subject_name, total_lessons, total_units, preview_colour, is_custom}]}
    """
    # Standard curriculum subjects for this year
    lessons_qs = (
        Lesson.objects.filter(year=child.school_year, is_custom=False)
        .values("key_stage", "subject_name")
        .annotate(
            total_lessons=Count("id"), total_units=Count("unit_slug", distinct=True)
        )
        .order_by("key_stage", "subject_name")
    )

    # Custom subjects created by this parent for this year
    custom_qs = (
        Lesson.objects.filter(is_custom=True, created_by=user, year=child.school_year)
        .values("subject_name")
        .annotate(
            total_lessons=Count("id"), total_units=Count("unit_slug", distinct=True)
        )
        .order_by("subject_name")
    )

    grouped = {}
    colour_index = 0

    for row in lessons_qs:
        grouped.setdefault(row["key_stage"], []).append(
            {
                "subject_name": row["subject_name"],
                "total_lessons": row["total_lessons"],
                "total_units": row["total_units"],
                "preview_colour": SUBJECT_COLOUR_PALETTE[
                    colour_index % len(SUBJECT_COLOUR_PALETTE)
                ],
                "is_custom": False,
            }
        )
        colour_index += 1

    for row in custom_qs:
        grouped.setdefault("Custom", []).append(
            {
                "subject_name": row["subject_name"],
                "total_lessons": row["total_lessons"],
                "total_units": row["total_units"],
                "preview_colour": SUBJECT_COLOUR_PALETTE[
                    colour_index % len(SUBJECT_COLOUR_PALETTE)
                ],
                "is_custom": True,
            }
        )
        colour_index += 1

    return grouped


def _subject_query_keys(subject, child):
    """Return canonical subject/year keys used for lesson lookups."""
    source_subject = (getattr(subject, "source_subject_name", "") or "").strip()
    query_subject = source_subject or subject.subject_name
    query_year = subject.source_year if subject.source_year else child.school_year
    return query_subject, query_year


def _subject_curriculum_stats(subject, child):
    """Return counts and source metadata for one enrolled subject."""
    query_subject, query_year = _subject_query_keys(subject, child)
    stats_qs = Lesson.objects.filter(subject_name=query_subject, year=query_year)
    return {
        "total_lessons": stats_qs.count(),
        "total_units": stats_qs.values("unit_slug").distinct().count(),
        "query_subject": query_subject,
        "query_year": query_year,
    }


def _active_course_enrollments_for_child(child):
    return list(
        child.course_enrollments.select_related("course")
        .filter(status="active")
        .order_by("-enrolled_at", "-id")
    )


def _sync_course_subject_configs(child, enrolled_subjects):
    active_enrollments = _active_course_enrollments_for_child(child)
    if not active_enrollments:
        return

    for enrollment in active_enrollments:
        course = enrollment.course
        fallback_days = list(course.default_days or []) or list(
            range(max(course.frequency_days, 1))
        )
        valid_days = set(range(max(course.frequency_days, 1)))

        for subject in enrolled_subjects:
            days = sorted(
                {
                    day
                    for day in (subject.days_of_week or fallback_days)
                    if day in valid_days
                }
            )
            if not days:
                days = fallback_days
            CourseSubjectConfig.objects.update_or_create(
                course=course,
                subject_name=subject.subject_name,
                defaults={
                    "key_stage": subject.key_stage,
                    "year": child.school_year,
                    "lessons_per_week": max(1, min(10, subject.lessons_per_week or 3)),
                    "days_of_week": days,
                    "colour_hex": subject.colour_hex,
                    "source": (
                        "csv"
                        if (subject.source_year or subject.source_subject_name)
                        else "oak"
                    ),
                    "source_subject_name": subject.source_subject_name
                    or subject.subject_name,
                    "source_year": subject.source_year,
                    "is_active": True,
                },
            )


@role_required("parent")
def subject_selection_view(request, child_id):
    """Step 1 of 2: parent picks subjects; lessons-per-week is set on the next page.

    GET: flat table of all subjects sorted by lesson count (desc).
    Sortable client-side by name, units, or lessons.

    POST: creates ``EnrolledSubject`` rows with default lessons_per_week=3
    (overridden on the day-assignment page), then redirects there.
    """
    child = get_object_or_404(Child, pk=child_id)

    if child.parent != request.user:
        return HttpResponseForbidden("You do not have permission to manage this child.")

    grouped = _build_subject_groups(child, request.user)

    if request.method == "POST":
        selected_subjects = request.POST.getlist("subjects")
        if not selected_subjects:
            messages.error(request, "Please select at least one subject.")
            subjects = sorted(
                [s for ks_subjects in grouped.values() for s in ks_subjects],
                key=lambda s: s["total_lessons"],
                reverse=True,
            )
            return render(
                request,
                "scheduler/subject_selection.html",
                {
                    "child": child,
                    "subjects": subjects,
                },
            )

        # Delete any existing enrolments before recreating
        child.enrolled_subjects.all().delete()

        # Flatten all subjects in palette order (key_stage alpha, subject alpha)
        all_subjects_ordered = [
            s["subject_name"] for ks_subjects in grouped.values() for s in ks_subjects
        ]

        to_create = []
        for subject_name in selected_subjects:
            key_stage = (
                Lesson.objects.filter(year=child.school_year, subject_name=subject_name)
                .values_list("key_stage", flat=True)
                .first()
                or "Custom"
            )
            palette_index = (
                all_subjects_ordered.index(subject_name)
                if subject_name in all_subjects_ordered
                else len(to_create)
            )
            to_create.append(
                EnrolledSubject(
                    child=child,
                    subject_name=subject_name,
                    key_stage=key_stage,
                    lessons_per_week=3,  # default; overridden in step 2
                    days_of_week=[0, 1, 2, 3, 4],  # default; overridden in step 2
                    colour_hex=SUBJECT_COLOUR_PALETTE[
                        palette_index % len(SUBJECT_COLOUR_PALETTE)
                    ],
                )
            )

        EnrolledSubject.objects.bulk_create(to_create)
        _sync_course_subject_configs(
            child,
            list(child.enrolled_subjects.filter(is_active=True)),
        )
        return redirect("scheduler:schedule_days", child_id=child.pk)

    subjects = sorted(
        [s for ks_subjects in grouped.values() for s in ks_subjects],
        key=lambda s: s["total_lessons"],
        reverse=True,
    )
    return render(
        request,
        "scheduler/subject_selection.html",
        {
            "child": child,
            "subjects": subjects,
        },
    )


@role_required("parent")
def schedule_days_view(request, child_id):
    """Step 2 of 2: set lessons-per-week and assign days for each enrolled subject.

    GET: table showing each enrolled subject with curriculum stats,
    a lessons-per-week number input, and Mon–Fri day checkboxes.

    POST: reads ``lpw_<pk>`` (lessons per week) and ``days_<pk>`` checkboxes,
    updates both fields on each ``EnrolledSubject``, then redirects to the
    generate-schedule confirmation.
    """
    child = get_object_or_404(Child, pk=child_id)

    if child.parent != request.user:
        return HttpResponseForbidden("You do not have permission to manage this child.")

    enrolled_subjects = list(child.enrolled_subjects.filter(is_active=True))

    if not enrolled_subjects:
        messages.error(request, "Please select at least one subject first.")
        return redirect("scheduler:subject_selection", child_id=child.pk)

    if request.method == "POST":
        day_choices_vals = [0, 1, 2, 3, 4]
        for subject in enrolled_subjects:
            raw_days = request.POST.getlist(f"days_{subject.pk}")
            days = sorted(
                {int(d) for d in raw_days if d.isdigit() and int(d) in day_choices_vals}
            )
            if not days:
                days = day_choices_vals
            subject.days_of_week = days

            raw_lpw = request.POST.get(f"lpw_{subject.pk}", "")
            if raw_lpw:
                try:
                    subject.lessons_per_week = max(1, min(10, int(raw_lpw)))
                except (ValueError, TypeError):
                    pass

            subject.save(update_fields=["days_of_week", "lessons_per_week"])

        _sync_course_subject_configs(child, enrolled_subjects)

        active_enrollments = _active_course_enrollments_for_child(child)
        if active_enrollments:
            return redirect(
                "planning:oak_wizard", course_id=active_enrollments[0].course_id
            )
        return redirect("scheduler:generate_schedule", child_id=child.pk)

    day_choices = [(0, "Mon"), (1, "Tue"), (2, "Wed"), (3, "Thu"), (4, "Fri")]

    subject_rows = []
    for subject in enrolled_subjects:
        checked = set(subject.days_of_week)
        if not checked:
            checked = {0, 1, 2, 3, 4}
        stats = _subject_curriculum_stats(subject, child)
        subject_rows.append(
            {
                "subject": subject,
                "checked_days": checked,
                "total_lessons": stats["total_lessons"],
                "total_units": stats["total_units"],
                "query_subject": stats["query_subject"],
                "query_year": stats["query_year"],
            }
        )

    return render(
        request,
        "scheduler/schedule_days.html",
        {
            "child": child,
            "subject_rows": subject_rows,
            "day_choices": day_choices,
        },
    )


@role_required("parent")
def custom_subject_view(request, child_id):
    """Three-path custom subject creator: import from another year, manual entry, or CSV.

    Import path creates EnrolledSubject rows with source_year so the
    scheduler pulls lessons from the original year.

    Manual and CSV paths bulk-create ``Lesson`` rows with ``is_custom=True``
    and link them to a ``CustomSubjectGroup`` for easy management later.
    All lessons are also immediately enrolled for ``child``.
    """
    child = get_object_or_404(Child, pk=child_id, parent=request.user)

    raw_years = (
        Lesson.objects.filter(is_custom=False).values_list("year", flat=True).distinct()
    )
    all_years = sorted(
        set(raw_years),
        key=lambda y: int(y.split()[-1]) if y.split()[-1].isdigit() else 99,
    )

    year_subjects = {}
    for yr in all_years:
        year_subjects[yr] = sorted(
            Lesson.objects.filter(year=yr, is_custom=False)
            .values_list("subject_name", flat=True)
            .distinct()
        )

    # Distinct key stages for dropdowns
    key_stages = sorted(
        Lesson.objects.filter(is_custom=False)
        .values_list("key_stage", flat=True)
        .distinct()
    )

    if request.method == "POST":
        tab = request.POST.get("tab", "")

        # ── TAB 1: Import one or more subjects from another year ──────────────
        if tab == "import_year":
            source_year = request.POST.get("source_year", "").strip()
            subject_names = request.POST.getlist("import_subjects")
            if not source_year or not subject_names:
                messages.error(
                    request, "Please select a year group and at least one subject."
                )
            else:
                imported = 0
                for subject_name in subject_names:
                    lesson_count = Lesson.objects.filter(
                        year=source_year, subject_name=subject_name, is_custom=False
                    ).count()
                    if lesson_count == 0:
                        continue
                    display_name = f"{subject_name} (from {source_year})"
                    placeholder_url = f"custom://import/{uuid.uuid4()}"
                    Lesson.objects.get_or_create(
                        lesson_url=placeholder_url,
                        defaults=dict(
                            key_stage="Custom",
                            subject_name=display_name,
                            programme_slug="custom",
                            year=child.school_year,
                            unit_slug="import",
                            unit_title="Imported",
                            lesson_number=1,
                            lesson_title=f"Import placeholder for {display_name}",
                            is_custom=True,
                            created_by=request.user,
                        ),
                    )
                    EnrolledSubject.objects.update_or_create(
                        child=child,
                        subject_name=display_name,
                        defaults=dict(
                            key_stage="Custom",
                            lessons_per_week=3,
                            days_of_week=[0, 1, 2, 3, 4],
                            source_subject_name=subject_name,
                            source_year=source_year,
                            colour_hex=SUBJECT_COLOUR_PALETTE[
                                child.enrolled_subjects.count()
                                % len(SUBJECT_COLOUR_PALETTE)
                            ],
                            is_active=True,
                        ),
                    )
                    imported += 1

                if imported:
                    messages.success(
                        request,
                        f"{imported} subject(s) imported from {source_year} — "
                        "now set lessons/week and choose days.",
                    )
                    return redirect("scheduler:subject_selection", child_id=child.pk)
                else:
                    messages.error(
                        request, "No lessons found for the selected subjects."
                    )

        # ── TAB 2: Manual entry ───────────────────────────────────────────────
        elif tab == "manual":
            subject_name = request.POST.get("manual_subject_name", "").strip()
            key_stage = (
                request.POST.get("manual_key_stage", "Custom").strip() or "Custom"
            )
            unit_title = (
                request.POST.get("manual_unit_title", "").strip() or subject_name
            )
            lesson_titles = request.POST.getlist("lesson_title[]")
            lesson_urls = request.POST.getlist("lesson_url[]")
            lesson_titles = [t.strip() for t in lesson_titles if t.strip()]

            if not subject_name:
                messages.error(request, "Please enter a subject name.")
            elif not lesson_titles:
                messages.error(request, "Please add at least one lesson.")
            else:
                group = CustomSubjectGroup.objects.create(
                    parent=request.user,
                    subject_name=subject_name,
                    year=child.school_year,
                )
                to_create = []
                for i, title in enumerate(lesson_titles, start=1):
                    raw_url = (
                        lesson_urls[i - 1].strip() if i <= len(lesson_urls) else ""
                    )
                    url = raw_url if raw_url else f"custom://manual/{uuid.uuid4()}"
                    to_create.append(
                        Lesson(
                            key_stage=key_stage,
                            subject_name=subject_name,
                            programme_slug="custom",
                            year=child.school_year,
                            unit_slug="manual",
                            unit_title=unit_title,
                            lesson_number=i,
                            lesson_title=title,
                            lesson_url=url,
                            is_custom=True,
                            created_by=request.user,
                            custom_group=group,
                        )
                    )
                Lesson.objects.bulk_create(to_create, ignore_conflicts=True)
                messages.success(
                    request,
                    f'{len(to_create)} lessons created for "{subject_name}". '
                    "Now enrol it and choose its days.",
                )
                return redirect("scheduler:subject_selection", child_id=child.pk)

        # ── TAB 3: CSV upload ─────────────────────────────────────────────────
        elif tab == "csv":
            subject_name = request.POST.get("csv_subject_name", "").strip()
            key_stage = request.POST.get("csv_key_stage", "Custom").strip() or "Custom"
            csv_file = request.FILES.get("csv_file")
            if not subject_name:
                messages.error(request, "Please enter a subject name.")
            elif not csv_file:
                messages.error(request, "Please upload a CSV file.")
            else:
                try:
                    decoded = csv_file.read().decode("utf-8-sig")
                    reader = csv.DictReader(io.StringIO(decoded))
                    group = CustomSubjectGroup.objects.create(
                        parent=request.user,
                        subject_name=subject_name,
                        year=child.school_year,
                    )
                    to_create = []
                    for i, row in enumerate(reader, start=1):
                        title = (row.get("lesson_title") or "").strip()
                        if not title:
                            continue
                        unit = (row.get("unit_title") or subject_name).strip()
                        raw_url = (row.get("lesson_url") or "").strip()
                        url = raw_url if raw_url else f"custom://csv/{uuid.uuid4()}"
                        try:
                            lesson_num = int(row.get("lesson_number") or i)
                        except (ValueError, TypeError):
                            lesson_num = i
                        to_create.append(
                            Lesson(
                                key_stage=key_stage,
                                subject_name=subject_name,
                                programme_slug="custom",
                                year=child.school_year,
                                unit_slug="csv",
                                unit_title=unit,
                                lesson_number=lesson_num,
                                lesson_title=title,
                                lesson_url=url,
                                is_custom=True,
                                created_by=request.user,
                                custom_group=group,
                            )
                        )
                    if not to_create:
                        group.delete()
                        messages.error(
                            request,
                            "No valid rows found. Check the lesson_title column.",
                        )
                    else:
                        Lesson.objects.bulk_create(to_create, ignore_conflicts=True)
                        messages.success(
                            request,
                            f'{len(to_create)} lessons created from CSV for "{subject_name}". '
                            "Now enrol it and choose its days.",
                        )
                        return redirect(
                            "scheduler:subject_selection", child_id=child.pk
                        )
                except Exception:
                    messages.error(
                        request, "Could not parse the CSV. Check the file format."
                    )

    return render(
        request,
        "scheduler/custom_subject.html",
        {
            "child": child,
            "all_years": all_years,
            "year_subjects_json": json.dumps(year_subjects),
            "key_stages": key_stages,
            "child_year": child.school_year,
        },
    )
