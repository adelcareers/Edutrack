import datetime

from django.contrib import messages
from django.db.models import Max
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.decorators import role_required_any
from courses.models import (
    AssignmentType,
    Course,
    sync_course_assignment_types_from_global,
)
from curriculum.models import Lesson
from edutrack.academic_calendar import ACADEMIC_WEEKS, WEEKDAYS_PER_WEEK
from scheduler.models import EnrolledSubject, ScheduledLesson

from .models import (
    AssignmentAttachment,
    AssignmentPlanItem,
    CourseAssignmentTemplate,
    StudentAssignment,
)


@role_required_any("parent", "teacher")
def plan_sessions_view(request):
    courses = list(
        Course.objects.filter(parent=request.user, is_archived=False).order_by("name")
    )
    cards = []
    for course in courses:
        days_per_week = WEEKDAYS_PER_WEEK
        week_rows = [
            {
                "week": week,
                "days": list(range(1, days_per_week + 1)),
            }
            for week in range(1, ACADEMIC_WEEKS + 1)
        ]
        cards.append(
            {
                "course": course,
                "week_rows": week_rows,
                "days_per_week": days_per_week,
                "weeks_count": ACADEMIC_WEEKS,
            }
        )
    return render(
        request,
        "planning/sessions.html",
        {
            "cards": cards,
        },
    )


@role_required_any("parent", "teacher")
def plan_course_view(request, course_id):
    course = get_object_or_404(Course, pk=course_id, parent=request.user)
    weeks = list(range(1, ACADEMIC_WEEKS + 1))
    days = list(range(1, WEEKDAYS_PER_WEEK + 1))

    sync_course_assignment_types_from_global(course)

    assignment_types = AssignmentType.objects.filter(
        course=course, is_hidden=False
    ).order_by("order", "name")

    def _safe_int(value, default):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _schedule_date_from_week_day(child, week_number, day_number):
        return child.academic_year_start + datetime.timedelta(
            days=(week_number - 1) * 7 + (day_number - 1)
        )

    def _lesson_query_for_subject(child, enrolled_subject):
        source_subject = (enrolled_subject.source_subject_name or "").strip()
        lesson_subject = source_subject or enrolled_subject.subject_name
        lesson_year = enrolled_subject.source_year or child.school_year
        return Lesson.objects.filter(
            subject_name=lesson_subject,
            year=lesson_year,
        ).order_by("unit_slug", "lesson_number")

    def _next_unscheduled_lesson(child, enrolled_subject):
        scheduled_ids = ScheduledLesson.objects.filter(
            child=child,
            enrolled_subject=enrolled_subject,
        ).values_list("lesson_id", flat=True)
        return _lesson_query_for_subject(child, enrolled_subject).exclude(
            id__in=scheduled_ids
        ).first()

    selected_week = _safe_int(request.GET.get("week", 1), 1) if weeks else 1
    selected_day = _safe_int(request.GET.get("day", 1), 1) if days else 1
    if selected_week not in weeks:
        selected_week = weeks[0] if weeks else 1
    if selected_day not in days:
        selected_day = days[0] if days else 1

    if request.method == "POST" and request.POST.get("delete_id"):
        delete_id = _safe_int(request.POST.get("delete_id"), None)
        if delete_id:
            plan_item = get_object_or_404(
                AssignmentPlanItem, pk=delete_id, course=course
            )
            template = plan_item.template
            if plan_item.scheduled_lesson_id:
                plan_item.scheduled_lesson.delete()
            plan_item.delete()
            template.delete()
        return redirect(f"{request.path}?week={selected_week}&day={selected_day}")

    if request.method == "POST":
        plan_item_id = _safe_int(request.POST.get("plan_item_id"), None)
        template_name = request.POST.get("assignment_name", "").strip()
        item_kind = (
            request.POST.get(
                "item_kind", CourseAssignmentTemplate.ITEM_KIND_ASSIGNMENT
            )
            .strip()
            .lower()
        )
        allowed_item_kinds = {
            CourseAssignmentTemplate.ITEM_KIND_ASSIGNMENT,
            CourseAssignmentTemplate.ITEM_KIND_ACTIVITY,
            CourseAssignmentTemplate.ITEM_KIND_LESSON,
        }
        if item_kind not in allowed_item_kinds:
            item_kind = CourseAssignmentTemplate.ITEM_KIND_ASSIGNMENT

        is_assignment_kind = item_kind == CourseAssignmentTemplate.ITEM_KIND_ASSIGNMENT
        is_lesson_kind = item_kind == CourseAssignmentTemplate.ITEM_KIND_LESSON
        type_id = request.POST.get("assignment_type") if is_assignment_kind else None
        week_number = _safe_int(
            request.POST.get("week_number", selected_week), selected_week
        )
        day_number = _safe_int(
            request.POST.get("day_number", selected_day), selected_day
        )
        due_in_days = _safe_int(request.POST.get("due_in_days", "0"), 0)
        view_mode = request.GET.get("view", "day")
        description = request.POST.get("description", "").strip()
        teacher_notes = request.POST.get("teacher_notes", "").strip()
        is_graded = request.POST.get("is_graded") == "on" if is_assignment_kind else False
        lesson_child_id = _safe_int(request.POST.get("lesson_child_id"), None)
        lesson_subject_id = _safe_int(request.POST.get("lesson_subject_id"), None)
        active_enrollments = list(
            course.enrollments.select_related("child").filter(status="active")
        )
        active_enrollment_ids = {enrollment.id for enrollment in active_enrollments}
        active_child_ids = {enrollment.child_id for enrollment in active_enrollments}

        selection_present = (
            request.POST.get("assign_enrollment_selection_present") == "1"
        )
        if is_assignment_kind and selection_present:
            selected_enrollment_ids = {
                _safe_int(value, -1)
                for value in request.POST.getlist("assign_enrollment_ids")
            }
            selected_enrollment_ids = {
                enrollment_id
                for enrollment_id in selected_enrollment_ids
                if enrollment_id in active_enrollment_ids
            }
        elif is_assignment_kind:
            # Backward compatibility for stale forms that don't send assignment toggles.
            selected_enrollment_ids = set(active_enrollment_ids)
        else:
            selected_enrollment_ids = set()

        if is_assignment_kind and not type_id:
            messages.error(request, "Please select an assignment type.")
            return redirect(
                f"{request.path}?week={week_number}&day={day_number}&view={view_mode}&create=1"
            )

        selected_lesson_child = None
        selected_lesson_subject = None
        if is_lesson_kind:
            if lesson_child_id not in active_child_ids:
                messages.error(request, "Please select a valid student for this lesson.")
                return redirect(
                    f"{request.path}?week={week_number}&day={day_number}&view={view_mode}&create=1"
                )

            selected_lesson_child = active_enrollments[0].child
            for enrollment in active_enrollments:
                if enrollment.child_id == lesson_child_id:
                    selected_lesson_child = enrollment.child
                    break

            selected_lesson_subject = EnrolledSubject.objects.filter(
                pk=lesson_subject_id,
                child=selected_lesson_child,
                is_active=True,
            ).first()
            if selected_lesson_subject is None:
                messages.error(request, "Please select a valid subject for this lesson.")
                return redirect(
                    f"{request.path}?week={week_number}&day={day_number}&view={view_mode}&create=1"
                )

        plan_item = None
        if template_name:
            assignment_type = None
            if is_assignment_kind:
                assignment_type = get_object_or_404(
                    AssignmentType,
                    pk=type_id,
                    course=course,
                    is_hidden=False,
                )

            if plan_item_id:
                plan_item = get_object_or_404(
                    AssignmentPlanItem,
                    pk=plan_item_id,
                    course=course,
                )
                template = plan_item.template
                template.item_kind = item_kind
                template.assignment_type = assignment_type
                template.name = template_name
                template.description = description
                template.is_graded = is_graded
                template.due_offset_days = due_in_days
                template.save()

                plan_item.week_number = week_number
                plan_item.day_number = day_number
                plan_item.due_in_days = due_in_days
                plan_item.notes = teacher_notes

                if is_lesson_kind:
                    scheduled_date = _schedule_date_from_week_day(
                        selected_lesson_child,
                        week_number,
                        day_number,
                    )

                    existing_scheduled_lesson = plan_item.scheduled_lesson
                    if (
                        existing_scheduled_lesson
                        and existing_scheduled_lesson.child_id
                        == selected_lesson_child.id
                        and existing_scheduled_lesson.enrolled_subject_id
                        == selected_lesson_subject.id
                    ):
                        existing_scheduled_lesson.scheduled_date = scheduled_date
                        existing_scheduled_lesson.save(update_fields=["scheduled_date"])
                        plan_item.lesson_child = selected_lesson_child
                        plan_item.lesson_enrolled_subject = selected_lesson_subject
                    else:
                        if existing_scheduled_lesson:
                            existing_scheduled_lesson.delete()

                        next_lesson = _next_unscheduled_lesson(
                            selected_lesson_child,
                            selected_lesson_subject,
                        )
                        if next_lesson is None:
                            messages.error(
                                request,
                                "No remaining OAK lessons are available for that subject.",
                            )
                            return redirect(
                                f"{request.path}?week={week_number}&day={day_number}&view={view_mode}&create=1"
                            )

                        next_order = (
                            ScheduledLesson.objects.filter(
                                child=selected_lesson_child,
                                scheduled_date=scheduled_date,
                            ).aggregate(max_order=Max("order_on_day"))["max_order"]
                            or -1
                        )
                        scheduled_lesson = ScheduledLesson.objects.create(
                            child=selected_lesson_child,
                            lesson=next_lesson,
                            enrolled_subject=selected_lesson_subject,
                            scheduled_date=scheduled_date,
                            order_on_day=next_order + 1,
                        )
                        plan_item.lesson_child = selected_lesson_child
                        plan_item.lesson_enrolled_subject = selected_lesson_subject
                        plan_item.scheduled_lesson = scheduled_lesson
                else:
                    if plan_item.scheduled_lesson_id:
                        plan_item.scheduled_lesson.delete()
                    plan_item.lesson_child = None
                    plan_item.lesson_enrolled_subject = None
                    plan_item.scheduled_lesson = None
                plan_item.save()
            else:
                template = CourseAssignmentTemplate.objects.create(
                    course=course,
                    item_kind=item_kind,
                    assignment_type=assignment_type,
                    name=template_name,
                    description=description,
                    is_graded=is_graded,
                    due_offset_days=due_in_days,
                    order=0,
                )
                plan_item = AssignmentPlanItem.objects.create(
                    course=course,
                    template=template,
                    week_number=week_number,
                    day_number=day_number,
                    due_in_days=due_in_days,
                    order=0,
                    notes=teacher_notes,
                )

                if is_lesson_kind:
                    next_lesson = _next_unscheduled_lesson(
                        selected_lesson_child,
                        selected_lesson_subject,
                    )
                    if next_lesson is None:
                        plan_item.delete()
                        template.delete()
                        messages.error(
                            request,
                            "No remaining OAK lessons are available for that subject.",
                        )
                        return redirect(
                            f"{request.path}?week={week_number}&day={day_number}&view={view_mode}&create=1"
                        )

                    scheduled_date = _schedule_date_from_week_day(
                        selected_lesson_child,
                        week_number,
                        day_number,
                    )
                    next_order = (
                        ScheduledLesson.objects.filter(
                            child=selected_lesson_child,
                            scheduled_date=scheduled_date,
                        ).aggregate(max_order=Max("order_on_day"))["max_order"]
                        or -1
                    )
                    scheduled_lesson = ScheduledLesson.objects.create(
                        child=selected_lesson_child,
                        lesson=next_lesson,
                        enrolled_subject=selected_lesson_subject,
                        scheduled_date=scheduled_date,
                        order_on_day=next_order + 1,
                    )
                    plan_item.lesson_child = selected_lesson_child
                    plan_item.lesson_enrolled_subject = selected_lesson_subject
                    plan_item.scheduled_lesson = scheduled_lesson
                    plan_item.save(
                        update_fields=[
                            "lesson_child",
                            "lesson_enrolled_subject",
                            "scheduled_lesson",
                        ]
                    )

            attachments = request.FILES.getlist("attachments")
            for attachment in attachments:
                AssignmentAttachment.objects.create(
                    plan_item=plan_item,
                    file=attachment,
                    original_name=attachment.name,
                )
            if attachments:
                messages.success(
                    request,
                    f"Uploaded {len(attachments)} attachment(s) successfully.",
                )

            if is_assignment_kind:
                for enrollment in active_enrollments:
                    base_date = enrollment.start_date + datetime.timedelta(
                        days=(week_number - 1) * 7 + (day_number - 1)
                    )
                    due_date = base_date + datetime.timedelta(days=due_in_days)

                    if enrollment.id in selected_enrollment_ids:
                        if plan_item_id:
                            student_assignment, _ = (
                                StudentAssignment.objects.get_or_create(
                                    enrollment=enrollment,
                                    plan_item=plan_item,
                                    defaults={
                                        "due_date": due_date,
                                        "status": "pending",
                                    },
                                )
                            )
                            if student_assignment.due_date != due_date:
                                student_assignment.due_date = due_date
                                student_assignment.save(update_fields=["due_date"])
                        else:
                            StudentAssignment.objects.create(
                                enrollment=enrollment,
                                plan_item=plan_item,
                                due_date=due_date,
                                status="pending",
                            )
                    else:
                        StudentAssignment.objects.filter(
                            enrollment=enrollment,
                            plan_item=plan_item,
                        ).delete()

                if plan_item_id:
                    for student_assignment in StudentAssignment.objects.filter(
                        plan_item=plan_item,
                        enrollment_id__in=selected_enrollment_ids,
                    ):
                        status_value = request.POST.get(
                            f"student_status_{student_assignment.id}",
                            "",
                        )
                        if status_value not in {"pending", "complete"}:
                            continue
                        student_assignment.status = status_value
                        if status_value == "complete":
                            student_assignment.completed_at = timezone.now()
                        else:
                            student_assignment.completed_at = None
                        student_assignment.save(update_fields=["status", "completed_at"])
            else:
                StudentAssignment.objects.filter(plan_item=plan_item).delete()

        if plan_item_id and template_name:
            return redirect(
                f"{request.path}?week={week_number}&day={day_number}&view={view_mode}&edit={plan_item_id}"
            )
        if template_name and plan_item is not None:
            return redirect(
                f"{request.path}?week={week_number}&day={day_number}&view={view_mode}&edit={plan_item.id}"
            )
        return redirect(f"{request.path}?week={week_number}&day={day_number}")

    plan_items = AssignmentPlanItem.objects.filter(course=course).select_related(
        "template",
        "template__assignment_type",
        "lesson_child",
        "lesson_enrolled_subject",
    )
    edit_id = _safe_int(request.GET.get("edit"), None)
    create_mode = request.GET.get("create") == "1" or bool(edit_id)
    editing_item = None
    editing_attachments = []
    student_assignments = []
    active_enrollments = list(
        course.enrollments.select_related("child").filter(status="active")
    )
    enrollment_rows = []

    if edit_id:
        editing_item = get_object_or_404(AssignmentPlanItem, pk=edit_id, course=course)
        selected_week = editing_item.week_number
        selected_day = editing_item.day_number
        editing_attachments = list(editing_item.attachments.all())
        student_assignments = list(
            editing_item.student_assignments.select_related("enrollment__child")
        )

    student_assignment_by_enrollment = {
        sa.enrollment_id: sa for sa in student_assignments
    }
    for enrollment in active_enrollments:
        student_assignment = student_assignment_by_enrollment.get(enrollment.id)
        enrollment_rows.append(
            {
                "enrollment": enrollment,
                "student_assignment": student_assignment,
                "assigned": bool(student_assignment) or not editing_item,
            }
        )

    lesson_child_options = []
    for enrollment in active_enrollments:
        child = enrollment.child
        if any(opt["id"] == child.id for opt in lesson_child_options):
            continue
        lesson_child_options.append(
            {
                "id": child.id,
                "name": child.first_name,
            }
        )

    lesson_subject_options = list(
        EnrolledSubject.objects.filter(
            child_id__in=[opt["id"] for opt in lesson_child_options],
            is_active=True,
        )
        .order_by("child__first_name", "subject_name")
        .values("id", "child_id", "subject_name")
    )
    day_items = plan_items.filter(
        week_number=selected_week,
        day_number=selected_day,
    )
    view_mode = request.GET.get("view", "day")
    if view_mode not in {"day", "all", "unscheduled"}:
        view_mode = "day"

    all_items = plan_items
    unscheduled_items = plan_items.none()

    if view_mode == "all":
        filtered_items = all_items
    elif view_mode == "unscheduled":
        filtered_items = unscheduled_items
    else:
        filtered_items = day_items

    plan_status_map = {}
    status_rows = StudentAssignment.objects.filter(plan_item__in=plan_items).values(
        "plan_item_id", "status", "due_date"
    )
    today = timezone.localdate()
    for row in status_rows:
        status = row["status"]
        if status != "complete" and row["due_date"] < today:
            status = "overdue"
        plan_status_map.setdefault(row["plan_item_id"], set()).add(status)
    for plan_item_id, statuses in plan_status_map.items():
        if "overdue" in statuses:
            plan_status_map[plan_item_id] = "overdue"
        elif statuses == {"complete"}:
            plan_status_map[plan_item_id] = "complete"
        else:
            plan_status_map[plan_item_id] = "pending"

    return render(
        request,
        "planning/detail.html",
        {
            "course": course,
            "weeks": weeks,
            "days": days,
            "assignment_types": assignment_types,
            "plan_items": filtered_items,
            "day_items": day_items,
            "selected_week": selected_week,
            "selected_day": selected_day,
            "day_count": day_items.count(),
            "unscheduled_count": unscheduled_items.count(),
            "all_count": all_items.count(),
            "view_mode": view_mode,
            "create_mode": create_mode,
            "editing_item": editing_item,
            "editing_attachments": editing_attachments,
            "student_assignments": student_assignments,
            "active_enrollments": active_enrollments,
            "enrollment_rows": enrollment_rows,
            "plan_status_map": plan_status_map,
            "item_kind_choices": [
                (CourseAssignmentTemplate.ITEM_KIND_ASSIGNMENT, "Assignment"),
                (CourseAssignmentTemplate.ITEM_KIND_ACTIVITY, "Activity"),
                (CourseAssignmentTemplate.ITEM_KIND_LESSON, "Lesson"),
            ],
            "lesson_child_options": lesson_child_options,
            "lesson_subject_options": lesson_subject_options,
        },
    )
