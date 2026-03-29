"""Schedule generation + editing views."""

import datetime

from django.contrib import messages
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import role_required
from curriculum.models import Lesson
from edutrack.academic_calendar import ACADEMIC_WEEKS, TOTAL_SCHOOL_DAYS
from scheduler.models import Child, ScheduledLesson
from scheduler.services import generate_schedule


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


@role_required("parent")
def generate_schedule_view(request, child_id):
    """Show a summary of subjects to be scheduled and, on POST, generate the schedule.

    GET: renders a confirmation page listing each enrolled subject with its
    curriculum lesson count.

    POST: deletes any existing ScheduledLesson rows for this child (idempotent
    regeneration), calls ``generate_schedule()``, flashes a success message
    containing the total count, then redirects to the child list.
    """
    child = get_object_or_404(Child, pk=child_id)

    if child.parent != request.user:
        return HttpResponseForbidden("You do not have permission to manage this child.")

    enrolled_subjects = list(child.enrolled_subjects.filter(is_active=True))
    existing_schedule_qs = child.scheduled_lessons.all()
    has_existing_schedule = existing_schedule_qs.exists()
    has_logged_lessons = existing_schedule_qs.filter(log__isnull=False).exists()
    has_evidence = existing_schedule_qs.filter(
        log__evidence_files__isnull=False
    ).exists()
    requires_replace_confirmation = has_logged_lessons or has_evidence

    if request.method == "POST":
        replace_confirmed = request.POST.get("confirm_replace_tracked") == "1"
        if requires_replace_confirmation and not replace_confirmed:
            messages.error(
                request,
                "This schedule has tracked lesson history. Confirm replacement before regenerating.",
            )
        else:
            child.scheduled_lessons.all().delete()
            count = generate_schedule(child, enrolled_subjects)
            messages.success(
                request,
                f"{child.first_name}'s schedule is ready — {count} lessons scheduled across {TOTAL_SCHOOL_DAYS} days ({ACADEMIC_WEEKS} weeks).",
            )
            return redirect("scheduler:child_list")

    subject_summaries = []
    for subject in enrolled_subjects:
        stats = _subject_curriculum_stats(subject, child)
        subject_summaries.append(
            {
                "subject": subject,
                "total_lessons": stats["total_lessons"],
                "total_units": stats["total_units"],
                "query_subject": stats["query_subject"],
                "query_year": stats["query_year"],
            }
        )

    return render(
        request,
        "scheduler/generate_schedule.html",
        {
            "child": child,
            "subject_summaries": subject_summaries,
            "has_existing_schedule": has_existing_schedule,
            "has_logged_lessons": has_logged_lessons,
            "has_evidence": has_evidence,
            "requires_replace_confirmation": requires_replace_confirmation,
        },
    )


@role_required("parent")
def schedule_edit_view(request, child_id):
    """Schedule editor: view, add, move, and delete individual ScheduledLesson rows.

    GET: lists all ScheduledLesson rows for the child grouped by date, with
    controls to delete individual rows or clear all rows for a subject.

    POST actions (via hidden ``action`` field):
    * ``delete_lesson`` — remove one ScheduledLesson by ``lesson_id``
    * ``delete_subject`` — remove all ScheduledLessons for an EnrolledSubject
    * ``clear_all`` — remove all ScheduledLessons for this child
    * ``move_lesson`` — change the ``scheduled_date`` of one ScheduledLesson
    """
    child = get_object_or_404(Child, pk=child_id, parent=request.user)

    if request.method == "POST":
        action = request.POST.get("action", "")

        if action == "delete_lesson":
            sl_id = request.POST.get("lesson_id")
            ScheduledLesson.objects.filter(pk=sl_id, child=child).delete()
            messages.success(request, "Lesson removed from schedule.")

        elif action == "delete_subject":
            es_id = request.POST.get("enrolled_subject_id")
            ScheduledLesson.objects.filter(
                enrolled_subject_id=es_id, child=child
            ).delete()
            messages.success(request, "All lessons for that subject removed.")

        elif action == "clear_all":
            count, _ = child.scheduled_lessons.all().delete()
            messages.success(request, f"Schedule cleared — {count} lessons removed.")

        elif action == "move_lesson":
            sl_id = request.POST.get("lesson_id")
            new_date = request.POST.get("new_date", "").strip()
            try:
                parsed = datetime.date.fromisoformat(new_date)
                ScheduledLesson.objects.filter(pk=sl_id, child=child).update(
                    scheduled_date=parsed
                )
                messages.success(request, "Lesson rescheduled.")
            except (ValueError, TypeError):
                messages.error(request, "Invalid date — use YYYY-MM-DD format.")

        return redirect("scheduler:schedule_edit", child_id=child.pk)

    # GET: group lessons by date
    scheduled = child.scheduled_lessons.select_related(
        "lesson", "enrolled_subject"
    ).order_by("scheduled_date", "order_on_day")

    # Group by date for template rendering
    from itertools import groupby

    grouped_schedule = []
    for date, group in groupby(scheduled, key=lambda sl: sl.scheduled_date):
        grouped_schedule.append(
            {
                "date": date,
                "lessons": list(group),
            }
        )

    enrolled_subjects = child.enrolled_subjects.filter(is_active=True)
    total = child.scheduled_lessons.count()

    return render(
        request,
        "scheduler/schedule_edit.html",
        {
            "child": child,
            "grouped_schedule": grouped_schedule,
            "enrolled_subjects": enrolled_subjects,
            "total": total,
        },
    )
