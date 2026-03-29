import datetime

from django.contrib import messages
from django.db.models import Max
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from accounts.decorators import role_required_any
from courses.models import (
    AssignmentType,
    Course,
    sync_course_assignment_types_from_global,
)
from curriculum.models import Lesson
from scheduler.models import EnrolledSubject, ScheduledLesson
from scheduler.services import generate_schedule

from .models import (
    ActivityProgress,
    ActivityProgressAttachment,
    AssignmentAttachment,
    AssignmentPlanItem,
    CourseAssignmentTemplate,
    StudentAssignment,
)


@role_required_any("parent", "teacher")
def initiate_oak_scheduling_view(request, course_id):
    import logging

    logger = logging.getLogger(__name__)
    try:
        course = get_object_or_404(Course, pk=course_id, parent=request.user)
        active_enrollments = list(
            course.enrollments.select_related("child").filter(status="active")
        )
        children = {enrollment.child for enrollment in active_enrollments}
        scheduled_count = 0
        for child in children:
            child_enrollments = [
                enr for enr in active_enrollments if enr.child_id == child.id
            ]
            scheduled_count += generate_schedule(child, child_enrollments)
        messages.success(
            request,
            f"OAK lesson scheduling complete. {scheduled_count} lessons scheduled.",
        )
        return HttpResponseRedirect(reverse("planning:plan_course", args=[course_id]))
    except Exception as e:
        logger.exception(
            "Error during OAK lesson scheduling for course_id=%s", course_id
        )
        messages.error(
            request,
            f"An error occurred during OAK lesson scheduling: {str(e)}. Please contact support.",
        )
        return HttpResponseRedirect(reverse("planning:plan_course", args=[course_id]))


WORKFLOW_ASSIGNMENTS = "assignments"
WORKFLOW_LESSONS = "lessons"
WORKFLOW_ACTIVITIES = "activities"

WORKFLOW_TO_ITEM_KIND = {
    WORKFLOW_ASSIGNMENTS: CourseAssignmentTemplate.ITEM_KIND_ASSIGNMENT,
    WORKFLOW_LESSONS: CourseAssignmentTemplate.ITEM_KIND_LESSON,
    WORKFLOW_ACTIVITIES: CourseAssignmentTemplate.ITEM_KIND_ACTIVITY,
}
ITEM_KIND_TO_WORKFLOW = {
    item_kind: workflow for workflow, item_kind in WORKFLOW_TO_ITEM_KIND.items()
}


def _safe_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_scope(raw_scope):
    return raw_scope if raw_scope in {"day", "all"} else "day"


def _normalize_workflow(raw_workflow):
    return (
        raw_workflow if raw_workflow in WORKFLOW_TO_ITEM_KIND else WORKFLOW_ASSIGNMENTS
    )


def _course_weeks(course):
    return list(range(1, max(course.duration_weeks, 1) + 1))


def _course_days(course):
    return list(range(1, max(course.frequency_days, 1) + 1))


def _build_plan_url(path, week, day, workflow, scope, create=False, edit_id=None):
    query = [f"week={week}", f"day={day}", f"workflow={workflow}", f"scope={scope}"]
    if create:
        query.append("create=1")
    if edit_id:
        query.append(f"edit={edit_id}")
    return f"{path}?{'&'.join(query)}"


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
    return (
        _lesson_query_for_subject(child, enrolled_subject)
        .exclude(id__in=scheduled_ids)
        .first()
    )


def _activity_status_from_rows(rows):
    statuses = {row.status for row in rows}
    if statuses and statuses == {"complete"}:
        return "complete"
    if statuses:
        return "pending"
    return None


def _lesson_provenance(plan_item):
    enrolled_subject = plan_item.lesson_enrolled_subject
    scheduled_lesson = plan_item.scheduled_lesson
    lesson = getattr(scheduled_lesson, "lesson", None)
    if enrolled_subject and (
        (enrolled_subject.source_year or "").strip()
        or (enrolled_subject.source_subject_name or "").strip()
    ):
        return {"label": "Imported", "css": "imported"}
    if lesson and lesson.is_custom:
        return {"label": "Manual", "css": "manual"}
    if lesson:
        return {"label": "Oak", "css": "oak"}
    return None


@role_required_any("parent", "teacher")
def plan_sessions_view(request):
    courses = list(
        Course.objects.filter(parent=request.user, is_archived=False).order_by("name")
    )
    cards = []
    for course in courses:
        week_rows = [
            {
                "week": week,
                "days": list(range(1, max(course.frequency_days, 1) + 1)),
            }
            for week in range(1, max(course.duration_weeks, 1) + 1)
        ]
        cards.append(
            {
                "course": course,
                "week_rows": week_rows,
                "days_per_week": course.frequency_days,
                "weeks_count": course.duration_weeks,
            }
        )
    return render(request, "planning/sessions.html", {"cards": cards})


@role_required_any("parent", "teacher")
def plan_course_view(request, course_id):
    course = get_object_or_404(Course, pk=course_id, parent=request.user)
    weeks = _course_weeks(course)
    days = _course_days(course)

    sync_course_assignment_types_from_global(course)

    assignment_types = AssignmentType.objects.filter(
        course=course,
        is_hidden=False,
    ).order_by("order", "name")

    selected_week = _safe_int(request.GET.get("week", 1), 1) if weeks else 1
    selected_day = _safe_int(request.GET.get("day", 1), 1) if days else 1
    if selected_week not in weeks:
        selected_week = weeks[0] if weeks else 1
    if selected_day not in days:
        selected_day = days[0] if days else 1

    workflow = _normalize_workflow(request.GET.get("workflow", WORKFLOW_ASSIGNMENTS))
    scope = _normalize_scope(request.GET.get("scope", "day"))

    active_enrollments = list(
        course.enrollments.select_related("child").filter(status="active")
    )
    active_enrollment_ids = {enrollment.id for enrollment in active_enrollments}
    active_child_ids = {enrollment.child_id for enrollment in active_enrollments}

    if request.method == "POST" and request.POST.get("delete_id"):
        delete_id = _safe_int(request.POST.get("delete_id"), None)
        workflow = _normalize_workflow(request.POST.get("workflow", workflow))
        scope = _normalize_scope(request.POST.get("scope", scope))
        week_number = _safe_int(
            request.POST.get("week_number", selected_week), selected_week
        )
        day_number = _safe_int(
            request.POST.get("day_number", selected_day), selected_day
        )
        if delete_id:
            plan_item = get_object_or_404(
                AssignmentPlanItem, pk=delete_id, course=course
            )
            template = plan_item.template
            if plan_item.scheduled_lesson_id:
                plan_item.scheduled_lesson.delete()
            plan_item.delete()
            template.delete()
        return redirect(
            _build_plan_url(
                request.path,
                week_number,
                day_number,
                workflow,
                scope,
            )
        )

    if request.method == "POST":
        workflow = _normalize_workflow(request.POST.get("workflow", workflow))
        scope = _normalize_scope(request.POST.get("scope", scope))
        plan_item_id = _safe_int(request.POST.get("plan_item_id"), None)
        template_name = request.POST.get("assignment_name", "").strip()
        item_kind = (
            request.POST.get("item_kind", WORKFLOW_TO_ITEM_KIND[workflow])
            .strip()
            .lower()
        )
        if item_kind not in ITEM_KIND_TO_WORKFLOW:
            item_kind = WORKFLOW_TO_ITEM_KIND[workflow]

        workflow = ITEM_KIND_TO_WORKFLOW[item_kind]
        is_assignment_kind = item_kind == CourseAssignmentTemplate.ITEM_KIND_ASSIGNMENT
        is_lesson_kind = item_kind == CourseAssignmentTemplate.ITEM_KIND_LESSON
        is_activity_kind = item_kind == CourseAssignmentTemplate.ITEM_KIND_ACTIVITY

        type_id = request.POST.get("assignment_type") if is_assignment_kind else None
        week_number = _safe_int(
            request.POST.get("week_number", selected_week), selected_week
        )
        day_number = _safe_int(
            request.POST.get("day_number", selected_day), selected_day
        )
        if week_number not in weeks:
            week_number = selected_week
        if day_number not in days:
            day_number = selected_day

        due_in_days = _safe_int(request.POST.get("due_in_days", "0"), 0)
        description = request.POST.get("description", "").strip()
        teacher_notes = request.POST.get("teacher_notes", "").strip()
        is_graded = (
            request.POST.get("is_graded") == "on" if is_assignment_kind else False
        )

        lesson_child_id = _safe_int(request.POST.get("lesson_child_id"), None)
        lesson_subject_id = _safe_int(request.POST.get("lesson_subject_id"), None)

        selected_assignment_enrollment_ids = set()
        assignment_selection_present = (
            request.POST.get("assign_enrollment_selection_present") == "1"
        )
        if is_assignment_kind and assignment_selection_present:
            selected_assignment_enrollment_ids = {
                _safe_int(value, -1)
                for value in request.POST.getlist("assign_enrollment_ids")
            }
            selected_assignment_enrollment_ids = {
                enrollment_id
                for enrollment_id in selected_assignment_enrollment_ids
                if enrollment_id in active_enrollment_ids
            }
        elif is_assignment_kind:
            selected_assignment_enrollment_ids = set(active_enrollment_ids)

        selected_activity_enrollment_ids = set()
        activity_selection_present = (
            request.POST.get("activity_enrollment_selection_present") == "1"
        )
        if is_activity_kind and activity_selection_present:
            selected_activity_enrollment_ids = {
                _safe_int(value, -1)
                for value in request.POST.getlist("activity_enrollment_ids")
            }
            selected_activity_enrollment_ids = {
                enrollment_id
                for enrollment_id in selected_activity_enrollment_ids
                if enrollment_id in active_enrollment_ids
            }

        if is_assignment_kind and not type_id:
            messages.error(request, "Please select an assignment type.")
            return redirect(
                _build_plan_url(
                    request.path,
                    week_number,
                    day_number,
                    workflow,
                    scope,
                    create=True,
                )
            )

        selected_lesson_child = None
        selected_lesson_subject = None
        if is_lesson_kind:
            if lesson_child_id not in active_child_ids:
                messages.error(
                    request, "Please select a valid student for this lesson."
                )
                return redirect(
                    _build_plan_url(
                        request.path,
                        week_number,
                        day_number,
                        workflow,
                        scope,
                        create=True,
                    )
                )

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
                messages.error(
                    request, "Please select a valid subject for this lesson."
                )
                return redirect(
                    _build_plan_url(
                        request.path,
                        week_number,
                        day_number,
                        workflow,
                        scope,
                        create=True,
                    )
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
                template.due_offset_days = due_in_days if is_assignment_kind else 0
                template.save()

                plan_item.week_number = week_number
                plan_item.day_number = day_number
                plan_item.due_in_days = due_in_days if is_assignment_kind else 0
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
                                "No remaining lessons are available for that subject.",
                            )
                            return redirect(
                                _build_plan_url(
                                    request.path,
                                    week_number,
                                    day_number,
                                    workflow,
                                    scope,
                                    create=True,
                                )
                            )

                        next_order = (
                            ScheduledLesson.objects.filter(
                                child=selected_lesson_child,
                                scheduled_date=scheduled_date,
                            ).aggregate(max_order=Max("order_on_day"))["max_order"]
                            or -1
                        )
                        plan_item.scheduled_lesson = ScheduledLesson.objects.create(
                            child=selected_lesson_child,
                            lesson=next_lesson,
                            enrolled_subject=selected_lesson_subject,
                            scheduled_date=scheduled_date,
                            order_on_day=next_order + 1,
                        )
                        plan_item.lesson_child = selected_lesson_child
                        plan_item.lesson_enrolled_subject = selected_lesson_subject
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
                    due_offset_days=due_in_days if is_assignment_kind else 0,
                    order=0,
                )
                plan_item = AssignmentPlanItem.objects.create(
                    course=course,
                    template=template,
                    week_number=week_number,
                    day_number=day_number,
                    due_in_days=due_in_days if is_assignment_kind else 0,
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
                            "No remaining lessons are available for that subject.",
                        )
                        return redirect(
                            _build_plan_url(
                                request.path,
                                week_number,
                                day_number,
                                workflow,
                                scope,
                                create=True,
                            )
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
                    plan_item.lesson_child = selected_lesson_child
                    plan_item.lesson_enrolled_subject = selected_lesson_subject
                    plan_item.scheduled_lesson = ScheduledLesson.objects.create(
                        child=selected_lesson_child,
                        lesson=next_lesson,
                        enrolled_subject=selected_lesson_subject,
                        scheduled_date=scheduled_date,
                        order_on_day=next_order + 1,
                    )
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

            if is_assignment_kind:
                for enrollment in active_enrollments:
                    base_date = enrollment.start_date + datetime.timedelta(
                        days=(week_number - 1) * 7 + (day_number - 1)
                    )
                    due_date = base_date + datetime.timedelta(days=due_in_days)
                    if enrollment.id in selected_assignment_enrollment_ids:
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
                            updates = []
                            if student_assignment.due_date != due_date:
                                student_assignment.due_date = due_date
                                updates.append("due_date")
                            status_value = request.POST.get(
                                f"student_status_{student_assignment.id}",
                                student_assignment.status,
                            )
                            if (
                                status_value in {"pending", "complete"}
                                and student_assignment.status != status_value
                            ):
                                student_assignment.status = status_value
                                student_assignment.completed_at = (
                                    timezone.now()
                                    if status_value == "complete"
                                    else None
                                )
                                updates.extend(["status", "completed_at"])
                            if updates:
                                student_assignment.save(update_fields=updates)
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
            else:
                StudentAssignment.objects.filter(plan_item=plan_item).delete()

            if is_activity_kind:
                for enrollment in active_enrollments:
                    if enrollment.id in selected_activity_enrollment_ids:
                        progress, _ = ActivityProgress.objects.get_or_create(
                            enrollment=enrollment,
                            plan_item=plan_item,
                        )
                        status_value = request.POST.get(
                            f"activity_status_{enrollment.id}",
                            progress.status,
                        )
                        if status_value not in {"pending", "complete"}:
                            status_value = "pending"
                        progress.notes = request.POST.get(
                            f"activity_notes_{enrollment.id}",
                            progress.notes,
                        ).strip()
                        progress.status = status_value
                        progress.completed_at = (
                            timezone.now() if status_value == "complete" else None
                        )
                        progress.save()

                        external_url = request.POST.get(
                            f"activity_link_{enrollment.id}",
                            "",
                        ).strip()
                        if external_url:
                            ActivityProgressAttachment.objects.create(
                                progress=progress,
                                external_url=external_url,
                            )
                        for attachment in request.FILES.getlist(
                            f"activity_files_{enrollment.id}"
                        ):
                            ActivityProgressAttachment.objects.create(
                                progress=progress,
                                file=attachment,
                                original_name=attachment.name,
                            )
                    else:
                        ActivityProgress.objects.filter(
                            enrollment=enrollment,
                            plan_item=plan_item,
                        ).delete()
            else:
                ActivityProgress.objects.filter(plan_item=plan_item).delete()

        if plan_item_id and template_name:
            return redirect(
                _build_plan_url(
                    request.path,
                    week_number,
                    day_number,
                    workflow,
                    scope,
                    create=True,
                    edit_id=plan_item_id,
                )
            )
        if template_name and plan_item is not None:
            return redirect(
                _build_plan_url(
                    request.path,
                    week_number,
                    day_number,
                    workflow,
                    scope,
                    create=True,
                    edit_id=plan_item.id,
                )
            )
        return redirect(
            _build_plan_url(request.path, week_number, day_number, workflow, scope)
        )

    plan_items = AssignmentPlanItem.objects.filter(course=course).select_related(
        "template",
        "template__assignment_type",
        "lesson_child",
        "lesson_enrolled_subject",
        "scheduled_lesson__lesson",
    )

    edit_id = _safe_int(request.GET.get("edit"), None)
    create_mode = request.GET.get("create") == "1" or bool(edit_id)
    editing_item = None
    editing_attachments = []
    student_assignments = []
    activity_progress_items = []

    if edit_id:
        editing_item = get_object_or_404(AssignmentPlanItem, pk=edit_id, course=course)
        selected_week = editing_item.week_number
        selected_day = editing_item.day_number
        workflow = ITEM_KIND_TO_WORKFLOW.get(
            editing_item.template.item_kind,
            workflow,
        )
        editing_attachments = list(editing_item.attachments.all())
        student_assignments = list(
            editing_item.student_assignments.select_related("enrollment__child")
        )
        activity_progress_items = list(
            editing_item.activity_progress_items.select_related(
                "enrollment__child"
            ).prefetch_related("attachments")
        )

    student_assignment_by_enrollment = {
        sa.enrollment_id: sa for sa in student_assignments
    }
    activity_progress_by_enrollment = {
        ap.enrollment_id: ap for ap in activity_progress_items
    }

    enrollment_rows = []
    activity_rows = []
    for enrollment in active_enrollments:
        student_assignment = student_assignment_by_enrollment.get(enrollment.id)
        activity_progress = activity_progress_by_enrollment.get(enrollment.id)
        enrollment_rows.append(
            {
                "enrollment": enrollment,
                "student_assignment": student_assignment,
                "assigned": bool(student_assignment) or not editing_item,
            }
        )
        activity_rows.append(
            {
                "enrollment": enrollment,
                "progress": activity_progress,
                "assigned": bool(activity_progress),
                "attachments": (
                    list(activity_progress.attachments.all())
                    if activity_progress
                    else []
                ),
            }
        )

    lesson_child_options = []
    for enrollment in active_enrollments:
        child = enrollment.child
        if any(opt["id"] == child.id for opt in lesson_child_options):
            continue
        lesson_child_options.append({"id": child.id, "name": child.first_name})

    lesson_subject_options = list(
        EnrolledSubject.objects.filter(
            child_id__in=[opt["id"] for opt in lesson_child_options],
            is_active=True,
        )
        .order_by("child__first_name", "subject_name")
        .values("id", "child_id", "subject_name", "source_year")
    )

    workflow_counts = {
        WORKFLOW_ASSIGNMENTS: plan_items.filter(
            template__item_kind=CourseAssignmentTemplate.ITEM_KIND_ASSIGNMENT
        ).count(),
        WORKFLOW_LESSONS: plan_items.filter(
            template__item_kind=CourseAssignmentTemplate.ITEM_KIND_LESSON
        ).count(),
        WORKFLOW_ACTIVITIES: plan_items.filter(
            template__item_kind=CourseAssignmentTemplate.ITEM_KIND_ACTIVITY
        ).count(),
    }

    workflow_items = plan_items.filter(
        template__item_kind=WORKFLOW_TO_ITEM_KIND[workflow]
    )
    day_items = workflow_items.filter(
        week_number=selected_week, day_number=selected_day
    )
    filtered_items = workflow_items if scope == "all" else day_items

    plan_status_map = {}
    status_rows = StudentAssignment.objects.filter(plan_item__in=plan_items).values(
        "plan_item_id",
        "status",
        "due_date",
    )
    today = timezone.localdate()
    for row in status_rows:
        status = row["status"]
        if status != "complete" and row["due_date"] < today:
            status = "overdue"
        plan_status_map.setdefault(row["plan_item_id"], set()).add(status)
    for plan_item_id, statuses in list(plan_status_map.items()):
        if "overdue" in statuses:
            plan_status_map[plan_item_id] = "overdue"
        elif statuses == {"complete"}:
            plan_status_map[plan_item_id] = "complete"
        else:
            plan_status_map[plan_item_id] = "pending"

    activity_status_rows = {}
    for progress in ActivityProgress.objects.filter(
        plan_item__in=plan_items
    ).select_related("enrollment__child"):
        activity_status_rows.setdefault(progress.plan_item_id, []).append(progress)
    for plan_item_id, rows in activity_status_rows.items():
        derived_status = _activity_status_from_rows(rows)
        if derived_status:
            plan_status_map[plan_item_id] = derived_status

    lesson_provenance_map = {}
    for plan_item in plan_items:
        provenance = _lesson_provenance(plan_item)
        if provenance:
            lesson_provenance_map[plan_item.id] = provenance

    workflow_tabs = [
        {
            "key": WORKFLOW_ASSIGNMENTS,
            "label": "Assignments",
            "count": workflow_counts[WORKFLOW_ASSIGNMENTS],
        },
        {
            "key": WORKFLOW_LESSONS,
            "label": "Lessons",
            "count": workflow_counts[WORKFLOW_LESSONS],
        },
        {
            "key": WORKFLOW_ACTIVITIES,
            "label": "Activities",
            "count": workflow_counts[WORKFLOW_ACTIVITIES],
        },
    ]

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
            "scope": scope,
            "scope_day_count": day_items.count(),
            "scope_all_count": workflow_items.count(),
            "workflow": workflow,
            "workflow_tabs": workflow_tabs,
            "create_mode": create_mode,
            "editing_item": editing_item,
            "editing_attachments": editing_attachments,
            "student_assignments": student_assignments,
            "active_enrollments": active_enrollments,
            "enrollment_rows": enrollment_rows,
            "activity_rows": activity_rows,
            "plan_status_map": plan_status_map,
            "lesson_provenance_map": lesson_provenance_map,
            "item_kind_choices": [
                (CourseAssignmentTemplate.ITEM_KIND_ASSIGNMENT, "Assignment"),
                (CourseAssignmentTemplate.ITEM_KIND_ACTIVITY, "Activity"),
                (CourseAssignmentTemplate.ITEM_KIND_LESSON, "Lesson"),
            ],
            "lesson_child_options": lesson_child_options,
            "lesson_subject_options": lesson_subject_options,
        },
    )
