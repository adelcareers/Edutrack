import datetime

from django.shortcuts import render
from django.contrib.auth.decorators import login_required

from accounts.decorators import role_required
from scheduler.models import ScheduledLesson


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

    return render(request, 'tracker/calendar.html', {
        'days': days,
        'year': year,
        'week': week,
        'today': today,
    })
