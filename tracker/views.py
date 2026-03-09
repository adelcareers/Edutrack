import datetime

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.contrib.auth.decorators import login_required

from accounts.decorators import role_required
from scheduler.models import ScheduledLesson
from tracker.models import LessonLog


@login_required
@role_required('student')
def calendar_view(request, year=None, week=None):
    """Weekly calendar for a student showing Mon–Fri lessons.

    URL params ``year`` and ``week`` are ISO year/week integers.
    Defaults to the current ISO week when omitted.
    """
    today = datetime.date.today()
    iso_year, iso_week, _ = today.isocalendar()
    if year is None or week is None:
        year, week = iso_year, iso_week

    monday = datetime.date.fromisocalendar(year, week, 1)
    friday = monday + datetime.timedelta(days=4)

    child = getattr(request.user, 'child_profile', None)

    lesson_by_date: dict = {}
    if child is not None:
        qs = (
            ScheduledLesson.objects
            .filter(child=child, scheduled_date__gte=monday, scheduled_date__lte=friday)
            .select_related('lesson', 'enrolled_subject', 'log')
        )
        for sl in qs:
            lesson_by_date.setdefault(sl.scheduled_date, []).append(sl)

    day_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday']
    days = {}
    for i, name in enumerate(day_names):
        date = monday + datetime.timedelta(days=i)
        days[name] = {
            'date': date,
            'lessons': lesson_by_date.get(date, []),
        }

    # Week navigation
    prev_monday = monday - datetime.timedelta(weeks=1)
    next_monday = monday + datetime.timedelta(weeks=1)
    prev_y, prev_w, _ = prev_monday.isocalendar()
    next_y, next_w, _ = next_monday.isocalendar()

    # Week display string e.g. "9–13 Jan 2026" or "30 Mar–3 Apr 2026"
    if monday.month == friday.month:
        week_display = f"{monday.day}–{friday.day} {friday.strftime('%b %Y')}"
    else:
        week_display = f"{monday.strftime('%-d %b')}–{friday.strftime('%-d %b %Y')}"

    return render(request, 'tracker/calendar.html', {
        'days': days,
        'year': year,
        'week': week,
        'today': today,
        'prev_year': prev_y,
        'prev_week': prev_w,
        'next_year': next_y,
        'next_week': next_w,
        'today_year': iso_year,
        'today_week': iso_week,
        'week_display': week_display,
    })


@login_required
@role_required('student')
def lesson_detail_view(request, scheduled_id):
    """Return JSON details for a single scheduled lesson.

    Ownership check: the lesson must belong to the student's child profile.
    """
    child = getattr(request.user, 'child_profile', None)
    sl = get_object_or_404(ScheduledLesson, pk=scheduled_id)

    if child is None or sl.child_id != child.pk:
        return JsonResponse({'error': 'forbidden'}, status=403)

    log = getattr(sl, 'log', None)
    evidence_count = sl.evidence_files.count() if hasattr(sl, 'evidence_files') else 0

    return JsonResponse({
        'id': sl.pk,
        'lesson_title': sl.lesson.lesson_title,
        'unit_title': sl.lesson.unit_title,
        'subject_name': sl.enrolled_subject.subject_name,
        'scheduled_date': sl.scheduled_date.strftime('%d %b %Y'),
        'lesson_url': sl.lesson.lesson_url,
        'colour_hex': sl.enrolled_subject.colour_hex,
        'status': log.status if log else 'pending',
        'mastery': log.mastery if log else 'unset',
        'student_notes': log.student_notes if log else '',
        'evidence_count': evidence_count,
    })
