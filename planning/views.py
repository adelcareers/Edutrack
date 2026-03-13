from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import role_required
from courses.models import Course, GlobalAssignmentType

from .models import AssignmentPlanItem, CourseAssignmentTemplate, CourseAssignmentType


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

    if not CourseAssignmentType.objects.filter(course=course).exists():
        global_types = (
            GlobalAssignmentType.objects
            .filter(parent=request.user)
            .order_by('order', 'name')
        )
        CourseAssignmentType.objects.bulk_create([
            CourseAssignmentType(
                course=course,
                global_type=gt,
                name=gt.name,
                color=gt.color,
                is_hidden=gt.is_hidden,
                order=gt.order,
            )
            for gt in global_types
        ])

    assignment_types = (
        CourseAssignmentType.objects
        .filter(course=course, is_hidden=False)
        .order_by('order', 'name')
    )

    def _safe_int(value, default):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    selected_week = _safe_int(request.GET.get('week', 1), 1) if weeks else 1
    selected_day = _safe_int(request.GET.get('day', 1), 1) if days else 1
    if selected_week not in weeks:
        selected_week = weeks[0] if weeks else 1
    if selected_day not in days:
        selected_day = days[0] if days else 1

    if request.method == 'POST':
        template_name = request.POST.get('assignment_name', '').strip()
        type_id = request.POST.get('assignment_type')
        week_number = _safe_int(request.POST.get('week_number', selected_week), selected_week)
        day_number = _safe_int(request.POST.get('day_number', selected_day), selected_day)
        due_in_days = _safe_int(request.POST.get('due_in_days', '0'), 0)
        description = request.POST.get('description', '').strip()
        is_graded = request.POST.get('is_graded') == 'on'

        if template_name and type_id:
            assignment_type = get_object_or_404(
                CourseAssignmentType,
                pk=type_id,
                course=course,
            )
            template = CourseAssignmentTemplate.objects.create(
                course=course,
                assignment_type=assignment_type,
                name=template_name,
                description=description,
                is_graded=is_graded,
                due_offset_days=due_in_days,
                order=0,
            )
            AssignmentPlanItem.objects.create(
                course=course,
                template=template,
                week_number=week_number,
                day_number=day_number,
                due_in_days=due_in_days,
                order=0,
            )
        return redirect(
            f"{request.path}?week={week_number}&day={day_number}"
        )

    plan_items = (
        AssignmentPlanItem.objects
        .filter(course=course)
        .select_related('template', 'template__assignment_type')
    )
    day_items = plan_items.filter(
        week_number=selected_week,
        day_number=selected_day,
    )
    view_mode = request.GET.get('view', 'day')
    if view_mode not in {'day', 'all', 'unscheduled'}:
        view_mode = 'day'

    all_items = plan_items
    unscheduled_items = plan_items.none()

    if view_mode == 'all':
        filtered_items = all_items
    elif view_mode == 'unscheduled':
        filtered_items = unscheduled_items
    else:
        filtered_items = day_items

    return render(request, 'planning/detail.html', {
        'course': course,
        'weeks': weeks,
        'days': days,
        'assignment_types': assignment_types,
        'plan_items': filtered_items,
        'day_items': day_items,
        'selected_week': selected_week,
        'selected_day': selected_day,
        'day_count': day_items.count(),
        'unscheduled_count': unscheduled_items.count(),
        'all_count': all_items.count(),
        'view_mode': view_mode,
    })
