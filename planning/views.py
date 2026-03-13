from django.shortcuts import get_object_or_404, render

from accounts.decorators import role_required
from courses.models import Course, GlobalAssignmentType

from .models import AssignmentPlanItem, CourseAssignmentType


@role_required('parent')
def plan_sessions_view(request):
    courses = list(
        Course.objects
        .filter(parent=request.user, is_archived=False)
        .order_by('name')
    )
    cards = []
    for course in courses:
        days_per_week = min(course.frequency_days, 5)
        week_rows = [
            {
                'week': week,
                'days': list(range(1, days_per_week + 1)),
            }
            for week in range(1, course.duration_weeks + 1)
        ]
        cards.append({
            'course': course,
            'week_rows': week_rows,
            'days_per_week': days_per_week,
        })
    return render(request, 'planning/sessions.html', {
        'cards': cards,
    })


@role_required('parent')
def plan_course_view(request, course_id):
    course = get_object_or_404(Course, pk=course_id, parent=request.user)
    weeks = list(range(1, course.duration_weeks + 1))
    days = list(range(1, min(course.frequency_days, 5) + 1))

    overrides = (
        CourseAssignmentType.objects
        .filter(course=course, is_hidden=False)
        .order_by('order', 'name')
    )
    if overrides.exists():
        assignment_types = overrides
    else:
        assignment_types = (
            GlobalAssignmentType.objects
            .filter(parent=request.user, is_hidden=False)
            .order_by('order', 'name')
        )

    plan_items = (
        AssignmentPlanItem.objects
        .filter(course=course)
        .select_related('template', 'template__assignment_type')
    )

    return render(request, 'planning/detail.html', {
        'course': course,
        'weeks': weeks,
        'days': days,
        'assignment_types': assignment_types,
        'plan_items': plan_items,
    })
