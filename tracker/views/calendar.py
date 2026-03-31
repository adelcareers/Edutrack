import datetime

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from accounts.decorators import role_required
from planning.models import ActivityProgress, StudentAssignment
from scheduler.models import ScheduledLesson, Vacation

from .assignments import _effective_assignment_status
from .utils import (
    _get_or_create_settings,
    _grid_calendar_date,
    _hydrate_activity_display,
    _hydrate_assignment_display,
)


def _build_calendar_context(
    child,
    year,
    week,
    today,
    is_readonly,
    child_id=None,
    child_name=None,
    first_day_of_week=0,
    show_empty_assignments=False,
    viewer_role=None,
):
    """Shared helper: build the full context dict for the calendar template.

    Covers Mon–Sat (6 days), queries lessons and vacations that overlap
    the week, and computes navigation years/weeks.
    """
    monday = datetime.date.fromisocalendar(year, week, 1)
    day_offset = first_day_of_week if first_day_of_week <= 5 else -1
    start_date = monday + datetime.timedelta(days=day_offset)
    end_date = start_date + datetime.timedelta(days=5)

    # Lessons
    lesson_by_date: dict = {}
    if child is not None:
        qs = ScheduledLesson.objects.filter(
            child=child, scheduled_date__gte=start_date, scheduled_date__lte=end_date
        ).select_related("lesson", "enrolled_subject", "log")
        for sl in qs:
            lesson_by_date.setdefault(sl.scheduled_date, []).append(sl)

    # Vacations overlapping this week
    vacations_by_date: dict = {}
    assignments_by_date: dict = {}
    if child is not None:
        vac_qs = Vacation.objects.filter(
            child=child,
            start_date__lte=end_date,
            end_date__gte=start_date,
        )
        for vac in vac_qs:
            cur = max(vac.start_date, monday)
            end = min(vac.end_date, end_date)
            while cur <= end:
                vacations_by_date.setdefault(cur, []).append(vac)
                cur += datetime.timedelta(days=1)

        assignment_qs = (
            StudentAssignment.objects.filter(
                enrollment__child=child,
                enrollment__status="active",
                due_date__gte=start_date,
                due_date__lte=end_date,
            )
            .select_related(
                "enrollment__course",
                "new_plan_item",
                "new_plan_item__assignment_detail__assignment_type",
            )
            .order_by("due_date", "id")
        )
        for assignment in assignment_qs:
            _hydrate_assignment_display(assignment)
            assignment.effective_status = _effective_assignment_status(
                assignment, today=today, viewer_role=viewer_role
            )
            assignments_by_date.setdefault(assignment.due_date, []).append(assignment)

    # Activities: compute calendar date from enrollment.start_date + grid position
    activities_by_date: dict = {}
    if child is not None:
        activity_qs = ActivityProgress.objects.filter(
            enrollment__child=child,
            enrollment__status="active",
        ).select_related("enrollment", "new_plan_item")
        for act in activity_qs:
            _hydrate_activity_display(act)
            act_date = act.display_date or _grid_calendar_date(
                act.enrollment,
                act.new_plan_item,
            )
            if act_date is None:
                continue
            if start_date <= act_date <= end_date:
                activities_by_date.setdefault(act_date, []).append(act)

    days = {}
    for i in range(6):
        date = start_date + datetime.timedelta(days=i)
        day_key = date.strftime("%A").lower()
        days[day_key] = {
            "date": date,
            "lessons": lesson_by_date.get(date, []),
            "vacations": vacations_by_date.get(date, []),
            "assignments": assignments_by_date.get(date, []),
            "activities": activities_by_date.get(date, []),
        }

    # Week navigation
    prev_start = start_date - datetime.timedelta(days=7)
    next_start = start_date + datetime.timedelta(days=7)
    prev_y, prev_w, _ = prev_start.isocalendar()
    next_y, next_w, _ = next_start.isocalendar()
    today_iso = today.isocalendar()

    # Header date range e.g. "Mar 09, 2026 — Mar 15, 2026"
    week_display = (
        f"{start_date.strftime('%b %d, %Y')} — {end_date.strftime('%b %d, %Y')}"
    )

    return {
        "days": days,
        "year": year,
        "week": week,
        "today": today,
        "prev_year": prev_y,
        "prev_week": prev_w,
        "next_year": next_y,
        "next_week": next_w,
        "today_year": today_iso[0],
        "today_week": today_iso[1],
        "week_display": week_display,
        "is_readonly": is_readonly,
        "child_id": child_id,
        "child_name": child_name,
        "child": child,
        "show_empty_assignments": show_empty_assignments,
        "first_day_of_week": first_day_of_week,
    }


@login_required
@role_required("student")
def calendar_view(request, year=None, week=None):
    """Weekly calendar for a student showing Mon–Sat lessons.

    URL params ``year`` and ``week`` are ISO year/week integers.
    Defaults to the current ISO week when omitted.
    """
    today = datetime.date.today()
    iso_year, iso_week, _ = today.isocalendar()
    if year is None or week is None:
        year, week = iso_year, iso_week

    child = getattr(request.user, "child_profile", None)
    parent = child.parent if child else None
    settings = _get_or_create_settings(parent) if parent else None
    ctx = _build_calendar_context(
        child,
        year,
        week,
        today,
        is_readonly=False,
        first_day_of_week=settings.first_day_of_week if settings else 0,
        show_empty_assignments=settings.show_empty_assignments if settings else False,
        viewer_role="student",
    )
    ctx["can_edit_assignments"] = True
    ctx["can_edit_lessons"] = True
    return render(request, "tracker/calendar.html", ctx)


@login_required
@role_required("parent")
def parent_calendar_home_view(request):
    """Redirect a parent to their first active child's calendar, or to
    the child list if they have no children yet."""
    from django.urls import reverse

    from scheduler.models import Child as ChildModel

    child = ChildModel.objects.filter(parent=request.user, is_active=True).first()
    if child:
        return redirect(
            reverse("tracker:parent_calendar", kwargs={"child_id": child.pk})
        )
    return redirect("scheduler:child_list")


@login_required
@role_required("parent")
def parent_calendar_view(request, child_id, year=None, week=None):
    """Read-only weekly calendar for a parent viewing their child's lessons.

    Ownership is verified: the child must belong to the requesting parent.
    Passes ``is_readonly=True`` so the template hides all action buttons.
    """
    from scheduler.models import Child as ChildModel

    child = get_object_or_404(ChildModel, pk=child_id)

    if child.parent_id != request.user.pk:
        from django.http import HttpResponseForbidden

        return HttpResponseForbidden()

    today = datetime.date.today()
    iso_year, iso_week, _ = today.isocalendar()
    if year is None or week is None:
        year, week = iso_year, iso_week

    from scheduler.models import Child as ChildModel

    siblings = list(ChildModel.objects.filter(parent=request.user, is_active=True))
    settings = _get_or_create_settings(request.user)

    ctx = _build_calendar_context(
        child,
        year,
        week,
        today,
        is_readonly=True,
        child_id=child_id,
        child_name=child.first_name,
        first_day_of_week=settings.first_day_of_week if settings else 0,
        show_empty_assignments=settings.show_empty_assignments if settings else False,
        viewer_role="parent",
    )
    ctx["can_edit_assignments"] = True
    ctx["can_edit_lessons"] = True
    ctx["siblings"] = siblings
    return render(request, "tracker/calendar.html", ctx)


def _build_ical(child, scheduled_lessons, vacations):
    """Build a minimal RFC 5545 iCalendar string for a child's schedule."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:-//EduTrack//Schedule for {child.first_name}//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{child.first_name} — EduTrack Schedule",
    ]

    for sl in scheduled_lessons:
        uid = f"lesson-{sl.pk}@edutrack"
        dtstart = sl.scheduled_date.strftime("%Y%m%d")
        dtend = (sl.scheduled_date + datetime.timedelta(days=1)).strftime("%Y%m%d")
        summary = f"{sl.enrolled_subject.subject_name}: {sl.lesson.lesson_title}"
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTART;VALUE=DATE:{dtstart}",
            f"DTEND;VALUE=DATE:{dtend}",
            f"SUMMARY:{summary}",
            "END:VEVENT",
        ]

    for vac in vacations:
        uid = f"vac-{vac.pk}@edutrack"
        dtstart = vac.start_date.strftime("%Y%m%d")
        dtend = (vac.end_date + datetime.timedelta(days=1)).strftime("%Y%m%d")
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTART;VALUE=DATE:{dtstart}",
            f"DTEND;VALUE=DATE:{dtend}",
            f"SUMMARY:{vac.name}",
            "TRANSP:TRANSPARENT",
            "END:VEVENT",
        ]

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


@login_required
@role_required("student")
def export_ical_view(request):
    """Download the student's full schedule as an iCalendar (.ics) file."""
    child = getattr(request.user, "child_profile", None)
    if child is None:
        from django.http import HttpResponseNotFound

        return HttpResponseNotFound("No child profile found.")

    lessons = (
        ScheduledLesson.objects.filter(child=child)
        .select_related("lesson", "enrolled_subject")
        .order_by("scheduled_date")
    )
    vacations = Vacation.objects.filter(child=child)

    content = _build_ical(child, lessons, vacations)
    response = HttpResponse(content, content_type="text/calendar; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="{child.first_name}_schedule.ics"'
    )
    return response


@login_required
@role_required("parent")
def parent_export_ical_view(request, child_id):
    """Download a child's full schedule as an iCalendar (.ics) file (parent)."""
    from scheduler.models import Child as ChildModel

    child = get_object_or_404(ChildModel, pk=child_id)

    if child.parent_id != request.user.pk:
        from django.http import HttpResponseForbidden

        return HttpResponseForbidden()

    lessons = (
        ScheduledLesson.objects.filter(child=child)
        .select_related("lesson", "enrolled_subject")
        .order_by("scheduled_date")
    )
    vacations = Vacation.objects.filter(child=child)

    content = _build_ical(child, lessons, vacations)
    response = HttpResponse(content, content_type="text/calendar; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="{child.first_name}_schedule.ics"'
    )
    return response
