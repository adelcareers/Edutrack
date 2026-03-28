import datetime
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from courses.models import AssignmentType, Course, Subject
from planning.models import (
    AssignmentAttachment,
    AssignmentComment,
    AssignmentSubmission,
    StudentAssignment,
)
from reports.services_gradebook import recalculate_enrollment_grade
from scheduler.models import Child
from .lessons import (
    _can_access_student_assignment,
    _effective_lesson_status,
    _lesson_status_meta,
)
from .utils import (
    _base_assignment_queryset_for_role,
    _base_lesson_queryset_for_role,
    _safe_int,
)


def _effective_assignment_status(assignment, today=None, viewer_role=None):
    """Resolve display status with automatic overdue behaviour."""
    if today is None:
        today = datetime.date.today()
    if assignment.status == "complete":
        return "done"
    if assignment.status == "needs_grading":
        if viewer_role == "student":
            return "done"
        return "needs_grading"
    if assignment.due_date < today:
        return "overdue"
    return "incomplete"


def _due_text(due_date, today):
    """Return human-readable due text for assignment cards."""
    delta = (due_date - today).days
    if delta == 0:
        return "Due today"
    if delta == 1:
        return "Due tomorrow"
    if delta > 1:
        return f"Due in {delta} days"
    if delta == -1:
        return "Due yesterday"
    return f"Due {abs(delta)} days ago"


def _can_grade_assignment(user):
    role = getattr(getattr(user, "profile", None), "role", None)
    return role in {"parent", "teacher"}


def _can_submit_assignment(user, assignment):
    role = getattr(getattr(user, "profile", None), "role", None)
    if role != "student":
        return False
    child = getattr(user, "child_profile", None)
    return child is not None and assignment.enrollment.child_id == child.pk


def _home_next_url(request, assignment=None):
    """Return safe redirect URL back to Home dashboard with selection context."""
    next_url = (request.POST.get("next") or "").strip()
    if next_url.startswith("/"):
        return next_url

    base = reverse("tracker:home_assignments")
    if assignment is None:
        return base
    return f"{base}?selected={assignment.pk}"


@login_required
def home_assignments_view(request):
    """Render a three-column, role-aware assignments/lessons dashboard."""
    role = getattr(getattr(request.user, "profile", None), "role", None)
    if role not in {"parent", "student", "teacher"}:
        return HttpResponseForbidden("You do not have permission to access this page.")

    today = timezone.localdate()
    active_tab = (request.GET.get("tab") or "lessons").strip().lower()
    if active_tab not in {"lessons", "assignments"}:
        active_tab = "lessons"

    selected_student_id = _safe_int(request.GET.get("student"))
    selected_course_id = _safe_int(request.GET.get("course"))
    selected_subject_id = _safe_int(request.GET.get("subject"))
    selected_type_id = _safe_int(request.GET.get("assignment_type"))
    selected_status = (request.GET.get("status") or "").strip().lower()
    hide_completed = request.GET.get("hide_completed", "1") in {"1", "true", "on"}
    selected_assignment_id = _safe_int(request.GET.get("selected"))
    selected_lesson_id = _safe_int(request.GET.get("selected_lesson"))

    assignment_scoped_qs = (
        _base_assignment_queryset_for_role(request.user, role)
        .select_related(
            "enrollment__child",
            "enrollment__course",
            "plan_item__template",
            "plan_item__template__assignment_type",
        )
        .order_by("due_date", "id")
    )
    assignment_total_count = assignment_scoped_qs.count()

    lesson_scoped_qs = _base_lesson_queryset_for_role(request.user, role)
    lesson_scoped_qs = lesson_scoped_qs.filter(scheduled_date__lte=today)
    lesson_total_count = lesson_scoped_qs.count()

    scoped_qs = assignment_scoped_qs
    lesson_qs = lesson_scoped_qs

    if role in {"parent", "teacher"} and selected_student_id:
        scoped_qs = scoped_qs.filter(enrollment__child_id=selected_student_id)
        lesson_qs = lesson_qs.filter(child_id=selected_student_id)

    if selected_course_id:
        scoped_qs = scoped_qs.filter(enrollment__course_id=selected_course_id)
        lesson_qs = lesson_qs.filter(
            child__course_enrollments__course_id=selected_course_id,
            child__course_enrollments__status="active",
        )

    selected_subject = None
    if selected_subject_id:
        selected_subject = Subject.objects.filter(pk=selected_subject_id).first()
        scoped_qs = scoped_qs.filter(
            enrollment__course__subjects__id=selected_subject_id
        )
        if selected_subject is not None:
            lesson_qs = lesson_qs.filter(
                enrolled_subject__subject_name=selected_subject.name
            )

    if selected_type_id:
        scoped_qs = scoped_qs.filter(
            plan_item__template__assignment_type_id=selected_type_id
        )

    scoped_qs = scoped_qs.distinct()
    lesson_qs = lesson_qs.distinct().order_by("scheduled_date", "id")

    assignments = list(scoped_qs)
    for assignment in assignments:
        assignment.effective_status = _effective_assignment_status(
            assignment, today=today, viewer_role=role
        )
        assignment.effective_status_label = assignment.effective_status.replace(
            "_", " "
        ).title()
        assignment.due_text = _due_text(assignment.due_date, today)

    lessons = []
    for sl in lesson_qs:
        lesson_status = _effective_lesson_status(
            getattr(sl, "log", None), sl.scheduled_date
        )
        if lesson_status == "skipped":
            continue
        sl.effective_status = lesson_status
        sl.effective_status_label = lesson_status.title()
        lessons.append(sl)

    if selected_status in {"done", "incomplete", "overdue", "needs_grading"}:
        assignments = [a for a in assignments if a.effective_status == selected_status]

    if selected_status in {"incomplete", "overdue", "complete"}:
        lessons = [
            lesson for lesson in lessons if lesson.effective_status == selected_status
        ]

    if hide_completed:
        assignments = [a for a in assignments if a.effective_status != "done"]
        lessons = [
            lesson for lesson in lessons if lesson.effective_status != "complete"
        ]

    base_query = request.GET.copy()
    if "selected" in base_query:
        del base_query["selected"]
    if "selected_lesson" in base_query:
        del base_query["selected_lesson"]

    for assignment in assignments:
        assignment_query = base_query.copy()
        assignment_query["tab"] = "assignments"
        assignment_query["selected"] = str(assignment.pk)
        assignment.select_url = f"?{assignment_query.urlencode()}"

    for sl in lessons:
        lesson_query = base_query.copy()
        lesson_query["tab"] = "lessons"
        lesson_query["selected_lesson"] = str(sl.pk)
        sl.select_url = f"?{lesson_query.urlencode()}"

    selected_assignment = None
    if selected_assignment_id is not None:
        selected_assignment = next(
            (a for a in assignments if a.pk == selected_assignment_id),
            None,
        )

    selected_lesson = None
    if selected_lesson_id is not None:
        selected_lesson = next(
            (lesson for lesson in lessons if lesson.pk == selected_lesson_id),
            None,
        )

    selected_attachments = []
    selected_comments = []
    selected_submissions = []
    if selected_assignment is not None:
        selected_attachments = list(
            AssignmentAttachment.objects.filter(
                plan_item=selected_assignment.plan_item
            ).order_by("created_at")
        )
        selected_comments = list(
            AssignmentComment.objects.filter(assignment=selected_assignment)
            .select_related("author")
            .order_by("created_at")
        )
        selected_submissions = list(
            AssignmentSubmission.objects.filter(assignment=selected_assignment)
            .select_related("uploaded_by")
            .order_by("-created_at")
        )
        selected_assignment.edit_url = (
            f"{reverse('planning:plan_course', args=[selected_assignment.enrollment.course.id])}"
            f"?edit={selected_assignment.plan_item_id}"
        )

    selected_lesson_log = (
        getattr(selected_lesson, "log", None) if selected_lesson else None
    )
    selected_lesson_comments = []
    selected_lesson_evidence_files = []
    selected_lesson_receipt_url = ""
    if selected_lesson is not None:
        selected_lesson_comments = list(
            selected_lesson.comments.select_related("author").order_by("-created_at")[
                :5
            ]
        )
        if selected_lesson_log is not None:
            selected_lesson_evidence_files = list(
                selected_lesson_log.evidence_files.all()[:5]
            )
            selected_lesson_receipt_url = selected_lesson_log.completion_receipt_url
        selected_lesson.status_label = _lesson_status_meta(
            selected_lesson.effective_status
        )["label"]
        selected_lesson.mastery = (
            selected_lesson_log.mastery if selected_lesson_log else "unset"
        )
        selected_lesson.student_notes = (
            selected_lesson_log.student_notes if selected_lesson_log else ""
        )

    base_options_qs = _base_assignment_queryset_for_role(request.user, role)
    base_lesson_options_qs = _base_lesson_queryset_for_role(request.user, role)

    student_options = []
    if role in {"parent", "teacher"}:
        student_options = list(
            Child.objects.filter(
                Q(course_enrollments__assignments__in=base_options_qs)
                | Q(scheduled_lessons__in=base_lesson_options_qs)
            )
            .distinct()
            .order_by("first_name")
        )

    course_options = list(
        Course.objects.filter(
            Q(enrollments__assignments__in=base_options_qs)
            | Q(enrollments__child__scheduled_lessons__in=base_lesson_options_qs)
        )
        .distinct()
        .order_by("name")
    )

    lesson_subject_names = list(
        base_lesson_options_qs.values_list("enrolled_subject__subject_name", flat=True)
    )

    subject_options = list(
        Subject.objects.filter(
            Q(courses__enrollments__assignments__in=base_options_qs)
            | Q(name__in=lesson_subject_names)
        )
        .distinct()
        .order_by("name")
    )

    type_options = list(
        AssignmentType.objects.filter(
            templates__plan_items__student_assignments__in=base_options_qs
        )
        .exclude(name__iexact="lesson")
        .distinct()
        .order_by("name")
    )

    selected_label = None
    if selected_assignment is not None:
        selected_label = selected_assignment.effective_status_label

    current_total_count = (
        lesson_total_count if active_tab == "lessons" else assignment_total_count
    )
    current_filtered_count = (
        len(lessons) if active_tab == "lessons" else len(assignments)
    )

    tab_base_query = request.GET.copy()
    tab_base_query.pop("tab", None)
    lesson_tab_query = tab_base_query.copy()
    lesson_tab_query["tab"] = "lessons"
    assignment_tab_query = tab_base_query.copy()
    assignment_tab_query["tab"] = "assignments"

    return render(
        request,
        "tracker/home_assignments.html",
        {
            "role": role,
            "active_tab": active_tab,
            "lessons": lessons,
            "selected_lesson": selected_lesson,
            "selected_lesson_log": selected_lesson_log,
            "selected_lesson_comments": selected_lesson_comments,
            "selected_lesson_evidence_files": selected_lesson_evidence_files,
            "selected_lesson_receipt_url": selected_lesson_receipt_url,
            "assignments": assignments,
            "selected_assignment": selected_assignment,
            "selected_status_label": selected_label,
            "total_count": current_total_count,
            "filtered_count": current_filtered_count,
            "student_options": student_options,
            "course_options": course_options,
            "subject_options": subject_options,
            "type_options": type_options,
            "selected_student_id": selected_student_id,
            "selected_course_id": selected_course_id,
            "selected_subject_id": selected_subject_id,
            "selected_type_id": selected_type_id,
            "selected_status": selected_status,
            "hide_completed": hide_completed,
            "today": today,
            "lesson_tab_url": f"?{lesson_tab_query.urlencode()}",
            "assignment_tab_url": f"?{assignment_tab_query.urlencode()}",
            "selected_attachments": selected_attachments,
            "selected_comments": selected_comments,
            "selected_submissions": selected_submissions,
            "can_grade": _can_grade_assignment(request.user),
            "can_edit_lessons": role in {"parent", "student", "teacher"},
            "can_submit": (
                _can_submit_assignment(request.user, selected_assignment)
                if selected_assignment is not None
                else False
            ),
            "next_url": request.get_full_path(),
        },
    )


@login_required
@require_POST
def home_assignment_status_view(request, assignment_id):
    """Update assignment completion status from Home details panel."""
    assignment = get_object_or_404(StudentAssignment, pk=assignment_id)
    if not _can_access_student_assignment(request.user, assignment):
        return HttpResponseForbidden()

    requested = (request.POST.get("status") or "").strip().lower()
    if requested not in {"done", "incomplete"}:
        return redirect(_home_next_url(request, assignment))

    if requested == "done":
        assignment.status = (
            "needs_grading"
            if getattr(getattr(request.user, "profile", None), "role", None)
            == "student"
            else "complete"
        )
        assignment.completed_at = timezone.now()
    else:
        assignment.status = "pending"
        assignment.completed_at = None

    assignment.save(update_fields=["status", "completed_at"])
    recalculate_enrollment_grade(assignment.enrollment)
    return redirect(_home_next_url(request, assignment))


@login_required
@require_POST
def home_assignment_grade_view(request, assignment_id):
    """Save grading fields from Home details panel (parent/teacher only)."""
    assignment = get_object_or_404(StudentAssignment, pk=assignment_id)
    if not _can_access_student_assignment(request.user, assignment):
        return HttpResponseForbidden()
    if not _can_grade_assignment(request.user):
        return HttpResponseForbidden()

    def _parse_decimal(raw):
        raw_value = (raw or "").strip()
        if raw_value == "":
            return None
        try:
            return Decimal(raw_value)
        except (InvalidOperation, ValueError):
            return None

    update_fields = []
    score_raw = request.POST.get("score")
    points_raw = request.POST.get("points_available")
    percent_raw = request.POST.get("score_percent")
    notes_raw = (request.POST.get("grading_notes") or "").strip()

    assignment.score = _parse_decimal(request.POST.get("score"))
    assignment.points_available = _parse_decimal(request.POST.get("points_available"))
    assignment.score_percent = _parse_decimal(request.POST.get("score_percent"))
    assignment.grading_notes = notes_raw
    assignment.graded_at = timezone.now()
    assignment.graded_by = request.user
    update_fields.extend(
        [
            "score",
            "points_available",
            "score_percent",
            "grading_notes",
            "graded_at",
            "graded_by",
        ]
    )

    status_raw = (request.POST.get("status") or "").strip()
    if status_raw in {"pending", "complete", "overdue", "needs_grading"}:
        assignment.status = status_raw
        update_fields.append("status")
        if status_raw in {"complete", "needs_grading"}:
            assignment.completed_at = timezone.now()
        else:
            assignment.completed_at = None
        update_fields.append("completed_at")

    has_grading_input = any(
        [
            (score_raw or "").strip(),
            (points_raw or "").strip(),
            (percent_raw or "").strip(),
            notes_raw,
        ]
    )
    if has_grading_input:
        assignment.status = "complete"
        assignment.completed_at = assignment.completed_at or timezone.now()
        update_fields.extend(["status", "completed_at"])

    due_date_raw = (request.POST.get("due_date") or "").strip()
    if due_date_raw:
        try:
            assignment.due_date = datetime.date.fromisoformat(due_date_raw)
            update_fields.append("due_date")
        except ValueError:
            pass

    assignment.save(update_fields=sorted(set(update_fields)))
    recalculate_enrollment_grade(assignment.enrollment)
    return redirect(_home_next_url(request, assignment))


@login_required
@require_POST
def home_assignment_comment_create_view(request, assignment_id):
    """Create shared thread comment for an assignment."""
    assignment = get_object_or_404(StudentAssignment, pk=assignment_id)
    if not _can_access_student_assignment(request.user, assignment):
        return HttpResponseForbidden()

    body = (request.POST.get("comment") or "").strip()
    if body:
        AssignmentComment.objects.create(
            assignment=assignment,
            author=request.user,
            body=body,
        )
    return redirect(_home_next_url(request, assignment))


@login_required
@require_POST
def home_assignment_submission_upload_view(request, assignment_id):
    """Upload student assignment file submission from Home details panel."""
    assignment = get_object_or_404(StudentAssignment, pk=assignment_id)
    if not _can_access_student_assignment(request.user, assignment):
        return HttpResponseForbidden()
    if not _can_submit_assignment(request.user, assignment):
        return HttpResponseForbidden()

    uploaded_file = request.FILES.get("submission")
    if uploaded_file is not None:
        AssignmentSubmission.objects.create(
            assignment=assignment,
            uploaded_by=request.user,
            file=uploaded_file,
            original_name=uploaded_file.name,
            content_type=(uploaded_file.content_type or "")[:120],
            file_size=getattr(uploaded_file, "size", 0) or 0,
        )
    return redirect(_home_next_url(request, assignment))


@login_required
def assignment_detail_view(request, assignment_id):
    """Return JSON details for one scheduled student assignment."""
    assignment = get_object_or_404(
        StudentAssignment.objects.select_related(
            "enrollment__child",
            "enrollment__course",
            "plan_item__template",
            "plan_item__template__assignment_type",
        ),
        pk=assignment_id,
    )

    if not _can_access_student_assignment(request.user, assignment):
        from django.http import JsonResponse

        return JsonResponse({"error": "forbidden"}, status=403)

    from django.http import JsonResponse

    role = getattr(getattr(request.user, "profile", None), "role", None)
    effective_status = _effective_assignment_status(assignment, viewer_role=role)
    return JsonResponse(
        {
            "id": assignment.pk,
            "course_name": assignment.enrollment.course.name,
            "child_name": assignment.enrollment.child.first_name,
            "assignment_name": assignment.plan_item.template.name,
            "assignment_type": assignment.plan_item.template.assignment_type.name,
            "due_date": assignment.due_date.strftime("%d %b %Y"),
            "effective_status": effective_status,
            "status_text": effective_status.replace("_", " ").title(),
            "notes": assignment.plan_item.notes,
        }
    )


@login_required
@require_POST
def update_assignment_status_view(request, assignment_id):
    """Accept POST {status: done|incomplete} and persist assignment state."""
    from django.http import JsonResponse

    assignment = get_object_or_404(
        StudentAssignment.objects.select_related("enrollment__child"),
        pk=assignment_id,
    )

    if not _can_access_student_assignment(request.user, assignment):
        return JsonResponse({"error": "forbidden"}, status=403)

    requested = request.POST.get("status", "").strip().lower()
    if requested not in {"done", "incomplete"}:
        return JsonResponse({"error": "invalid status"}, status=400)

    if requested == "done":
        assignment.status = (
            "needs_grading"
            if getattr(getattr(request.user, "profile", None), "role", None)
            == "student"
            else "complete"
        )
        assignment.completed_at = timezone.now()
    else:
        assignment.status = "pending"
        assignment.completed_at = None

    assignment.save(update_fields=["status", "completed_at"])
    role = getattr(getattr(request.user, "profile", None), "role", None)
    effective_status = _effective_assignment_status(assignment, viewer_role=role)
    return JsonResponse(
        {
            "success": True,
            "status": effective_status,
            "message": f"Assignment marked {effective_status}.",
        }
    )
