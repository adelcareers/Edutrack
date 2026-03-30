"""Courses views — implemented below."""

import csv
import json

from django.contrib import messages
from django.db import models, transaction
from django.db.models import Count
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import role_required
from scheduler.models import Child, ScheduledLesson
from tracker.models import LessonLog

from .forms import CompleteEnrollmentForm, CourseForm, EnrollStudentForm
from .models import (
    DEFAULT_ASSIGNMENT_TYPES,
    GRADE_YEAR_CHOICES,
    LEGACY_GRADE_YEAR_KEY_MAP,
    AssignmentType,
    Course,
    CourseArchive,
    CourseEnrollment,
    CourseSubjectConfig,
    GlobalAssignmentType,
    Subject,
    seed_global_assignment_types,
    sync_course_assignment_types_from_global,
)

# ── Helpers ────────────────────────────────────────────────────────────────


def _get_course_or_403(course_id, user):
    course = get_object_or_404(Course, pk=course_id)
    if course.parent != user:
        raise PermissionError
    return course


def _get_enrollment_or_403(enrollment_id, user):
    enrollment = get_object_or_404(CourseEnrollment, pk=enrollment_id)
    if enrollment.course.parent != user:
        raise PermissionError
    return enrollment


def _effective_assignment_status(student_assignment, today=None):
    """Resolve status with auto-overdue behaviour for incomplete work."""
    if today is None:
        today = timezone.localdate()
    if student_assignment.status == "complete":
        return "complete"
    if student_assignment.status == "needs_grading":
        return "needs_grading"
    if student_assignment.due_date < today:
        return "overdue"
    return "pending"


def _archive_course_snapshot(course, remark="course deleted"):
    """Persist full assignment-level history before hard deleting a course."""
    from planning.models import StudentAssignment

    enrollments = list(course.enrollments.select_related("child").order_by("id"))
    assignment_types = list(
        course.assignment_types.order_by("order", "name").values(
            "id", "name", "weight", "order"
        )
    )

    enrollment_history = []
    for enrollment in enrollments:
        enrollment_history.append(
            {
                "id": enrollment.id,
                "child_id": enrollment.child_id,
                "child_name": enrollment.child.first_name,
                "start_date": enrollment.start_date.isoformat(),
                "days_of_week": enrollment.days_of_week,
                "status": enrollment.status,
                "completed_school_year": enrollment.completed_school_year,
                "completed_calendar_year": enrollment.completed_calendar_year,
                "enrolled_at": (
                    enrollment.enrolled_at.isoformat()
                    if enrollment.enrolled_at
                    else None
                ),
                "completed_at": (
                    enrollment.completed_at.isoformat()
                    if enrollment.completed_at
                    else None
                ),
            }
        )

    student_assignments = (
        StudentAssignment.objects.filter(enrollment__course=course)
        .select_related(
            "enrollment__child",
            "plan_item__template",
            "plan_item__template__assignment_type",
        )
        .order_by("due_date", "id")
    )

    assignment_history = []
    today = timezone.localdate()
    for assignment in student_assignments:
        plan_item = assignment.plan_item
        template = plan_item.template
        assignment_type = template.assignment_type
        attachments = [
            {
                "id": a.id,
                "original_name": a.original_name,
                "file": str(a.file),
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in plan_item.attachments.all().order_by("id")
        ]

        assignment_history.append(
            {
                "student_assignment_id": assignment.id,
                "enrollment_id": assignment.enrollment_id,
                "child_id": assignment.enrollment.child_id,
                "child_name": assignment.enrollment.child.first_name,
                "due_date": assignment.due_date.isoformat(),
                "status": assignment.status,
                "effective_status": _effective_assignment_status(
                    assignment, today=today
                ),
                "completed_at": (
                    assignment.completed_at.isoformat()
                    if assignment.completed_at
                    else None
                ),
                "score": (
                    str(assignment.score) if assignment.score is not None else None
                ),
                "week_number": plan_item.week_number,
                "day_number": plan_item.day_number,
                "due_in_days": plan_item.due_in_days,
                "plan_notes": plan_item.notes,
                "template_name": template.name,
                "template_description": template.description,
                "is_graded": template.is_graded,
                "assignment_type": assignment_type.name,
                "assignment_type_id": assignment_type.id,
                "attachments": attachments,
            }
        )

    course_data = {
        "id": course.id,
        "name": course.name,
        "color": course.color,
        "description": course.description,
        "course_intro": course.course_intro,
        "duration_weeks": course.duration_weeks,
        "frequency_days": course.frequency_days,
        "default_days": course.default_days,
        "grading_style": course.grading_style,
        "use_assignment_weights": course.use_assignment_weights,
        "credits": str(course.credits) if course.credits is not None else None,
        "grade_years": course.grade_years,
        "is_archived": course.is_archived,
        "subjects": list(course.subjects.values("id", "name")),
        "labels": list(course.labels.values("id", "name", "color")),
        "assignment_types": assignment_types,
    }

    return CourseArchive.objects.create(
        parent=course.parent,
        original_course_id=course.id,
        course_name=course.name,
        remark=remark,
        course_data=course_data,
        enrollment_history=enrollment_history,
        assignment_history=assignment_history,
    )


# ── Course CRUD ────────────────────────────────────────────────────────────


@role_required("parent")
def course_list_view(request):
    tab = request.GET.get("tab", "active")
    is_archived = tab == "archived"

    qs = Course.objects.filter(
        parent=request.user, is_archived=is_archived
    ).prefetch_related("subjects", "labels", "enrollments")

    search = request.GET.get("q", "").strip()
    if search:
        qs = qs.filter(name__icontains=search)

    # Sidebar filter — enrolled student
    child_filter = request.GET.get("child", "")
    if child_filter:
        qs = qs.filter(
            enrollments__child__pk=child_filter, enrollments__status="active"
        ).distinct()

    # Sidebar filter — subject name
    subject_filter = request.GET.get("subject", "")
    if subject_filter:
        qs = qs.filter(subjects__pk=subject_filter).distinct()

    # Sidebar filter — grade year
    grade_filter = request.GET.get("grade", "").strip()
    if grade_filter:
        grade_filter = LEGACY_GRADE_YEAR_KEY_MAP.get(
            grade_filter.lower(),
            grade_filter,
        )
        qs = qs.filter(grade_years__icontains=grade_filter)

    courses = list(qs)

    children = Child.objects.filter(parent=request.user, is_active=True)
    subjects = Subject.objects.filter(parent=request.user)

    return render(
        request,
        "courses/course_list.html",
        {
            "courses": courses,
            "tab": tab,
            "search": search,
            "children": children,
            "subjects": subjects,
            "grade_year_choices": GRADE_YEAR_CHOICES,
            "child_filter": child_filter,
            "subject_filter": subject_filter,
            "grade_filter": grade_filter,
            "active_count": Course.objects.filter(
                parent=request.user, is_archived=False
            ).count(),
            "archived_count": Course.objects.filter(
                parent=request.user, is_archived=True
            ).count(),
        },
    )


@role_required("parent")
def course_new_view(request):
    seed_global_assignment_types(request.user)

    if request.method == "POST":
        form = CourseForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            course = form.save(commit=False)
            course.parent = request.user
            course.save()
            form.save_m2m()
            sync_course_assignment_types_from_global(course)
            _save_assignment_weights(request, course)

            messages.success(request, f'Course "{course.name}" created.')
            return redirect("courses:course_detail", course_id=course.pk)
    else:
        form = CourseForm(user=request.user)

    global_types = list(
        GlobalAssignmentType.objects.filter(parent=request.user, is_hidden=False)
        .order_by("order", "name")
        .values("id", "name", "color", "order")
    )
    posted_weights = {}
    if request.method == "POST":
        for key in request.POST:
            if not key.startswith("at_global_id_"):
                continue
            try:
                idx = int(key.split("_")[-1])
                global_id = int(request.POST.get(f"at_global_id_{idx}", "").strip())
            except (TypeError, ValueError):
                continue

            weight_raw = request.POST.get(f"at_weight_{idx}", "0")
            try:
                posted_weights[global_id] = max(0, min(100, int(weight_raw)))
            except ValueError:
                posted_weights[global_id] = 0

    assignment_types = [
        {
            "global_type_id": gt["id"],
            "name": gt["name"],
            "color": gt["color"],
            "order": gt["order"],
            "weight": posted_weights.get(gt["id"], 0),
            "is_hidden": False,
        }
        for gt in global_types
    ]

    return render(
        request,
        "courses/course_form.html",
        {
            "form": form,
            "editing": False,
            "default_assignment_types": DEFAULT_ASSIGNMENT_TYPES,
            "assignment_types": assignment_types,
        },
    )


@role_required("parent")
def course_detail_view(request, course_id):
    try:
        course = _get_course_or_403(course_id, request.user)
    except PermissionError:
        return HttpResponseForbidden("You do not have permission to view this course.")

    sync_course_assignment_types_from_global(course)

    enrollments = (
        CourseEnrollment.objects.filter(course=course)
        .select_related("child")
        .order_by("-enrolled_at")
    )
    active_enrollments = enrollments.filter(status="active")
    completed_enrollments = enrollments.filter(status="completed")
    assignment_types = course.assignment_types.filter(is_hidden=False)

    return render(
        request,
        "courses/course_detail.html",
        {
            "course": course,
            "enrollments": enrollments,
            "active_enrollments": active_enrollments,
            "completed_enrollments": completed_enrollments,
            "active_count": active_enrollments.count(),
            "completed_count": completed_enrollments.count(),
            "assignment_types": assignment_types,
            "grade_year_labels": course.get_grade_year_labels(),
        },
    )


@role_required("parent")
def course_edit_view(request, course_id):
    try:
        course = _get_course_or_403(course_id, request.user)
    except PermissionError:
        return HttpResponseForbidden("You do not have permission to edit this course.")

    if request.method == "POST":
        form = CourseForm(
            request.POST, request.FILES, instance=course, user=request.user
        )
        if form.is_valid():
            form.save()
            sync_course_assignment_types_from_global(course)
            _save_assignment_weights(request, course)
            messages.success(request, f'Course "{course.name}" updated.')
            return redirect("courses:course_detail", course_id=course.pk)
    else:
        form = CourseForm(instance=course, user=request.user)

    sync_course_assignment_types_from_global(course)

    enrollments = (
        CourseEnrollment.objects.filter(course=course)
        .select_related("child")
        .order_by("-enrolled_at")
    )
    active_enrollments = enrollments.filter(status="active")
    completed_enrollments = enrollments.filter(status="completed")

    child_ids = list(enrollments.values_list("child_id", flat=True).distinct())
    progress_by_child = {
        cid: {"total": 0, "completed": 0, "percent": 0} for cid in child_ids
    }
    if child_ids:
        totals = (
            ScheduledLesson.objects.filter(child_id__in=child_ids)
            .values("child_id")
            .annotate(total=Count("id"))
        )
        completes = (
            LessonLog.objects.filter(
                status="complete", scheduled_lesson__child_id__in=child_ids
            )
            .values("scheduled_lesson__child_id")
            .annotate(total=Count("id"))
        )
        for row in totals:
            progress_by_child[row["child_id"]]["total"] = row["total"]
        for row in completes:
            child_id = row["scheduled_lesson__child_id"]
            progress_by_child[child_id]["completed"] = row["total"]
        for child_id, data in progress_by_child.items():
            total = data["total"]
            completed = data["completed"]
            data["percent"] = round((completed / total) * 100) if total else 0

    active_enrollment_data = [
        {
            "enrollment": enrollment,
            "progress": progress_by_child.get(
                enrollment.child_id, {"total": 0, "completed": 0, "percent": 0}
            ),
        }
        for enrollment in active_enrollments
    ]
    completed_enrollment_data = [
        {
            "enrollment": enrollment,
            "progress": progress_by_child.get(
                enrollment.child_id, {"total": 0, "completed": 0, "percent": 0}
            ),
        }
        for enrollment in completed_enrollments
    ]

    return render(
        request,
        "courses/course_form.html",
        {
            "form": form,
            "course": course,
            "editing": True,
            "default_assignment_types": DEFAULT_ASSIGNMENT_TYPES,
            "assignment_types": list(
                course.assignment_types.filter(
                    global_type__isnull=False, global_type__is_hidden=False
                ).values(
                    "id",
                    "global_type_id",
                    "name",
                    "color",
                    "weight",
                    "order",
                    "is_hidden",
                )
            ),
            "enrollments": enrollments,
            "active_enrollment_data": active_enrollment_data,
            "completed_enrollment_data": completed_enrollment_data,
        },
    )


@role_required("parent")
@require_POST
def course_archive_view(request, course_id):
    try:
        course = _get_course_or_403(course_id, request.user)
    except PermissionError:
        return HttpResponseForbidden(
            "You do not have permission to archive this course."
        )

    course.is_archived = not course.is_archived
    course.save(update_fields=["is_archived"])
    action = "archived" if course.is_archived else "unarchived"
    messages.success(request, f'Course "{course.name}" {action}.')
    return redirect("courses:course_list")


@role_required("parent")
def course_export_view(request, course_id):
    try:
        course = _get_course_or_403(course_id, request.user)
    except PermissionError:
        return HttpResponseForbidden(
            "You do not have permission to export this course."
        )

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{course.name}.csv"'

    writer = csv.writer(response)
    writer.writerow(
        [
            "Course Name",
            "Duration (weeks)",
            "Frequency (days/week)",
            "Grading Style",
            "Credits",
            "Grade Years",
            "Subjects",
            "Description",
        ]
    )
    writer.writerow(
        [
            course.name,
            course.duration_weeks,
            course.frequency_days,
            course.get_grading_style_display(),
            course.credits or "",
            ", ".join(course.get_grade_year_labels()),
            ", ".join(s.name for s in course.subjects.all()),
            course.description,
        ]
    )

    if course.use_assignment_weights:
        writer.writerow([])
        writer.writerow(["Assignment Type", "Weight (%)"])
        for at in course.assignment_types.all():
            writer.writerow([at.name, at.weight])

    return response


@role_required("parent")
@require_POST
def course_delete_view(request, course_id):
    """Hard delete a course after archiving full assignment-level history."""
    try:
        course = _get_course_or_403(course_id, request.user)
    except PermissionError:
        return HttpResponseForbidden(
            "You do not have permission to delete this course."
        )

    course_name = course.name
    with transaction.atomic():
        from planning.models import (
            AssignmentAttachment,
            AssignmentPlanItem,
            CourseAssignmentTemplate,
            StudentAssignment,
        )

        _archive_course_snapshot(course, remark="course deleted")

        # Remove planning graph explicitly to satisfy PROTECT constraints.
        StudentAssignment.objects.filter(enrollment__course=course).delete()
        AssignmentAttachment.objects.filter(plan_item__course=course).delete()
        AssignmentPlanItem.objects.filter(course=course).delete()
        CourseAssignmentTemplate.objects.filter(course=course).delete()

        course.delete()

    messages.success(
        request,
        f'Course "{course_name}" deleted. Full assignment history has been archived.',
    )
    return redirect("courses:course_list")


@role_required("parent")
def archived_courses_view(request):
    """List deleted-course archives visible to the parent/teacher."""
    archives = CourseArchive.objects.filter(parent=request.user).order_by(
        "-archived_at"
    )
    return render(
        request,
        "courses/archived_courses.html",
        {
            "archives": archives,
        },
    )


@role_required("parent")
def archived_course_detail_view(request, archive_id):
    """Show full archived assignment history for one deleted course."""
    archive = get_object_or_404(CourseArchive, pk=archive_id, parent=request.user)
    return render(
        request,
        "courses/archived_course_detail.html",
        {
            "archive": archive,
            "assignment_count": len(archive.assignment_history),
            "enrollment_count": len(archive.enrollment_history),
        },
    )


# ── Enrollment ─────────────────────────────────────────────────────────────


@role_required("parent")
def enroll_student_view(request, course_id):
    try:
        course = _get_course_or_403(course_id, request.user)
    except PermissionError:
        return HttpResponseForbidden(
            "You do not have permission to enroll in this course."
        )

    if request.method == "POST":
        form = EnrollStudentForm(request.POST, user=request.user, course=course)
        if form.is_valid():
            enrollment = form.save(commit=False)
            enrollment.course = course
            days = form.cleaned_data["days_of_week"]
            enrollment.days_of_week = [int(d) for d in days]
            enrollment.save()
            messages.success(
                request, f'{enrollment.child.first_name} enrolled in "{course.name}".'
            )
            return redirect("courses:course_detail", course_id=course.pk)
    else:
        form = EnrollStudentForm(user=request.user, course=course)
        # Pre-select child if passed via query string
        child_id = request.GET.get("child_id")
        if child_id:
            try:
                form.fields["child"].initial = int(child_id)
            except (ValueError, TypeError):
                pass

    return render(
        request,
        "courses/enroll_student.html",
        {
            "form": form,
            "course": course,
        },
    )


@role_required("parent")
@require_POST
def unenroll_student_view(request, enrollment_id):
    try:
        enrollment = _get_enrollment_or_403(enrollment_id, request.user)
    except PermissionError:
        return HttpResponseForbidden(
            "You do not have permission to unenroll this student."
        )

    child_name = enrollment.child.first_name
    course_name = enrollment.course.name
    enrollment.status = "unenrolled"
    enrollment.save(update_fields=["status"])
    messages.warning(
        request,
        f'{child_name} has been unenrolled from "{course_name}". '
        "All associated data has been removed.",
    )
    return redirect("courses:course_detail", course_id=enrollment.course.pk)


@role_required("parent")
def complete_enrollment_view(request, enrollment_id):
    try:
        enrollment = _get_enrollment_or_403(enrollment_id, request.user)
    except PermissionError:
        return HttpResponseForbidden(
            "You do not have permission to complete this enrollment."
        )

    if request.method == "POST":
        form = CompleteEnrollmentForm(request.POST)
        if form.is_valid():
            enrollment.status = "completed"
            enrollment.completed_school_year = form.cleaned_data[
                "completed_school_year"
            ]
            enrollment.completed_calendar_year = form.cleaned_data[
                "completed_calendar_year"
            ]
            enrollment.completed_at = timezone.now()
            enrollment.save()
            messages.success(
                request,
                f'{enrollment.child.first_name} has completed "{enrollment.course.name}".',
            )
            return redirect("courses:course_detail", course_id=enrollment.course.pk)
    else:
        form = CompleteEnrollmentForm()

    return render(
        request,
        "courses/complete_enrollment.html",
        {
            "form": form,
            "enrollment": enrollment,
        },
    )


@role_required("parent")
@require_POST
def reactivate_enrollment_view(request, enrollment_id):
    try:
        enrollment = _get_enrollment_or_403(enrollment_id, request.user)
    except PermissionError:
        return HttpResponseForbidden(
            "You do not have permission to reactivate this enrollment."
        )

    enrollment.status = "active"
    enrollment.completed_school_year = ""
    enrollment.completed_calendar_year = None
    enrollment.completed_at = None
    enrollment.save(
        update_fields=[
            "status",
            "completed_school_year",
            "completed_calendar_year",
            "completed_at",
        ]
    )
    messages.success(
        request,
        f'{enrollment.child.first_name} has been reactivated in "{enrollment.course.name}".',
    )
    return redirect("courses:course_detail", course_id=enrollment.course.pk)


# ── Subject AJAX ───────────────────────────────────────────────────────────


@role_required("parent")
@require_POST
def subject_create_view(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid JSON"}, status=400)

    name = data.get("name", "").strip()
    if not name:
        return JsonResponse({"error": "name is required"}, status=400)
    if len(name) > 100:
        return JsonResponse({"error": "name too long"}, status=400)

    subject, created = Subject.objects.get_or_create(parent=request.user, name=name)
    return JsonResponse({"id": subject.pk, "name": subject.name, "created": created})


@role_required("parent")
def subject_list_view(request):
    subjects = list(Subject.objects.filter(parent=request.user).values("id", "name"))
    return JsonResponse({"subjects": subjects})


# ── Private helpers ────────────────────────────────────────────────────────


def _save_assignment_weights(request, course):
    """Persist only per-course weights for globally-defined assignment types."""
    globally_hidden_ids = set(
        GlobalAssignmentType.objects.filter(
            parent=course.parent, is_hidden=True
        ).values_list("id", flat=True)
    )

    indices = set()
    for key in request.POST:
        if key.startswith("at_id_") or key.startswith("at_global_id_"):
            try:
                indices.add(int(key.split("_")[-1]))
            except ValueError:
                continue

    for idx in sorted(indices):
        at_id = request.POST.get(f"at_id_{idx}", "").strip()
        at_global_id = request.POST.get(f"at_global_id_{idx}", "").strip()

        weight_raw = request.POST.get(f"at_weight_{idx}", "0")
        enabled = request.POST.get(f"at_enabled_{idx}") == "on"
        try:
            weight = max(0, min(100, int(weight_raw)))
        except ValueError:
            weight = 0

        is_hidden = not enabled
        try:
            global_type_id_int = int(at_global_id)
        except (TypeError, ValueError):
            global_type_id_int = None
        if global_type_id_int in globally_hidden_ids:
            is_hidden = True

        if at_id:
            AssignmentType.objects.filter(pk=at_id, course=course).update(
                weight=weight,
                is_hidden=is_hidden,
            )
            continue

        if at_global_id:
            AssignmentType.objects.filter(
                course=course,
                global_type_id=at_global_id,
            ).update(
                weight=weight,
                is_hidden=is_hidden,
            )


# ── CourseSubjectConfig soft/hard delete ───────────────────────────────────


@role_required("parent")
@require_POST
def subject_config_soft_delete_view(request, config_id):
    """Soft-delete a CourseSubjectConfig: hide future unstarted lessons."""
    from planning.models import PlanItem

    config = get_object_or_404(
        CourseSubjectConfig, pk=config_id, course__parent=request.user
    )
    config.is_active = False
    config.save(update_fields=["is_active"])
    PlanItem.objects.filter(
        models.Q(lesson_detail__course_subject=config)
        | models.Q(activity_detail__course_subject=config),
        is_active=True,
    ).update(is_active=False)
    messages.success(
        request,
        f'Subject "{config.subject_name}" hidden. Completed progress is preserved.',
    )
    return redirect("planning:plan_course", course_id=config.course_id)


@role_required("parent")
@require_POST
def subject_config_hard_delete_view(request, config_id):
    """Hard-delete a CourseSubjectConfig after confirmation.

    Requires the parent to type "DELETE" in the confirmation field.
    Cascades to related PlanItems and per-student records.
    """
    from planning.models import ActivityProgress, PlanItem, StudentAssignment

    config = get_object_or_404(
        CourseSubjectConfig, pk=config_id, course__parent=request.user
    )
    confirm = request.POST.get("confirm", "").strip()
    if confirm != "DELETE":
        messages.error(
            request,
            'Type "DELETE" to confirm permanent removal of this subject.',
        )
        return redirect("planning:plan_course", course_id=config.course_id)

    course_id = config.course_id
    subject_name = config.subject_name
    related_plan_items = list(
        PlanItem.objects.filter(
            models.Q(lesson_detail__course_subject=config)
            | models.Q(activity_detail__course_subject=config)
        )
    )
    related_plan_item_ids = [plan_item.id for plan_item in related_plan_items]
    StudentAssignment.objects.filter(new_plan_item_id__in=related_plan_item_ids).delete()
    ActivityProgress.objects.filter(new_plan_item_id__in=related_plan_item_ids).delete()
    PlanItem.objects.filter(id__in=related_plan_item_ids).delete()
    config.delete()
    messages.success(
        request,
        f'Subject "{subject_name}" and all related plan items have been deleted.',
    )
    return redirect("planning:plan_course", course_id=course_id)
