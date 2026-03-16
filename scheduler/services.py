"""Scheduling service for EduTrack.

This module contains the core algorithm that distributes Oak National Academy
curriculum lessons across a 180-school-day academic year for a given child.
The function is deliberately kept free of HTTP or Django view concerns so that
it can be called from tests, management commands, and web views alike.
"""

from datetime import timedelta
from typing import List

from curriculum.models import Lesson
from scheduler.models import EnrolledSubject, ScheduledLesson


def generate_schedule(child, enrolled_subjects: List[EnrolledSubject]) -> int:
    """Distribute all Oak curriculum lessons across 180 school weekdays.

    The algorithm works in four steps:

    1. **School-day list** — build a list of exactly 180 weekday dates
       (Monday–Friday) starting from ``child.academic_year_start``.

    2. **Lesson queues** — for each enrolled subject fetch all matching
       ``Lesson`` rows for ``child.school_year``, ordered by
       ``unit_slug`` then ``lesson_number`` so lessons are taught in
       curriculum order.

    3. **Round-robin distribution** — iterate over the 180 school days.
       At the start of each new ISO calendar week reset the per-subject
       lesson counter.  On each day, walk the enrolled subjects in order
       and schedule a lesson for any subject that still has remaining
       quota for that week and lessons left in its queue.

    4. **Bulk insert** — persist all ``ScheduledLesson`` objects in a
       single ``bulk_create`` call with ``batch_size=500`` to minimise
       round-trips to the database.

    Args:
        child: A ``Child`` model instance whose ``academic_year_start``
            and ``school_year`` fields must be set.
        enrolled_subjects: An iterable of ``EnrolledSubject`` instances
            belonging to ``child``.  Each must have ``lessons_per_week``
            set to a value between 1 and 5.

    Returns:
        The total number of ``ScheduledLesson`` records created.

    Raises:
        Nothing — if a subject's curriculum queue is exhausted before the
        180 days are filled it is silently skipped for the remaining days.
    """
    # STEP 1: Build school day list
    school_days = []
    current = child.academic_year_start
    while len(school_days) < 180:
        if current.weekday() < 5:  # Monday=0, Friday=4
            school_days.append(current)
        current += timedelta(days=1)

    # STEP 2: Build lesson queues per subject
    queues = {}
    for subject in enrolled_subjects:
        lesson_year = subject.source_year if subject.source_year else child.school_year
        queues[subject.id] = list(
            Lesson.objects.filter(
                subject_name=subject.subject_name, year=lesson_year
            ).order_by("unit_slug", "lesson_number")
        )

    # Parse days-of-week sets per subject (0=Mon … 4=Fri)
    subject_days = {}
    for subject in enrolled_subjects:
        parts = subject.days_of_week.split(",") if subject.days_of_week else []
        days = {int(d) for d in parts if d.isdigit() and 0 <= int(d) <= 4}
        subject_days[subject.id] = days if days else {0, 1, 2, 3, 4}

    # STEP 3: Compute slots-per-day per subject.
    # For subjects with lessons_per_week <= len(days), each selected day gets
    # at most 1 slot (distributed round-robin: first `extra` days get 1 extra).
    # For subjects with lessons_per_week > len(days), some days get multiple
    # slots using integer division + remainder.
    slots_per_day = {}  # {subject.id: {weekday_int: n_slots}}
    for subject in enrolled_subjects:
        days_list = sorted(subject_days[subject.id])
        if not days_list:
            days_list = [0, 1, 2, 3, 4]
        lpw = subject.lessons_per_week
        base, extra = divmod(lpw, len(days_list))
        sdict = {}
        for i, d in enumerate(days_list):
            sdict[d] = base + (1 if i < extra else 0)
        slots_per_day[subject.id] = sdict

    # STEP 4: Distribute using slots-per-day rules
    to_create = []
    # Track how many slots have been filled for this subject on *this* particular weekday
    # across the current ISO week.  Reset each new week.
    week_day_counts = {s.id: {} for s in enrolled_subjects}
    current_week = school_days[0].isocalendar()[1]

    for day in school_days:
        if day.isocalendar()[1] != current_week:
            week_day_counts = {s.id: {} for s in enrolled_subjects}
            current_week = day.isocalendar()[1]
        order = 0
        for subject in enrolled_subjects:
            wd = day.weekday()
            allowed = slots_per_day[subject.id].get(wd, 0)
            used = week_day_counts[subject.id].get(wd, 0)
            while used < allowed and queues[subject.id]:
                lesson = queues[subject.id].pop(0)
                to_create.append(
                    ScheduledLesson(
                        child=child,
                        lesson=lesson,
                        enrolled_subject=subject,
                        scheduled_date=day,
                        order_on_day=order,
                    )
                )
                used += 1
                order += 1
            week_day_counts[subject.id][wd] = used

    # STEP 4: Bulk insert
    ScheduledLesson.objects.bulk_create(to_create, batch_size=500)
    return len(to_create)
