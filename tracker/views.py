import datetime
import uuid
from decimal import Decimal, InvalidOperation
from urllib.parse import unquote, urlparse

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import role_required
from accounts.models import ParentSettings
from courses.models import AssignmentType, Course, Subject
from planning.models import (
    AssignmentAttachment,
    AssignmentComment,
    AssignmentSubmission,
    StudentAssignment,
)
from reports.services_gradebook import recalculate_enrollment_grade
from scheduler.models import Child, ScheduledLesson, Vacation
from tracker.models import EvidenceFile, LessonComment, LessonLog


def _get_or_create_settings(user):
    if user is None:
        return None
    settings, _ = ParentSettings.objects.get_or_create(user=user)
    return settings


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


def _safe_int(raw_value):
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return None


def _base_assignment_queryset_for_role(user, role):
    """Return active student assignments visible to the requesting user."""
    queryset = StudentAssignment.objects.filter(enrollment__status="active")
    if role == "student":
        child = getattr(user, "child_profile", None)
        if child is None:
            return StudentAssignment.objects.none()
        return queryset.filter(enrollment__child=child)

    if role in {"parent", "teacher"}:
        return queryset.filter(enrollment__course__parent=user)

    return StudentAssignment.objects.none()


def _base_lesson_queryset_for_role(user, role):
    """Return scheduled lessons visible to the requesting user role."""
    queryset = ScheduledLesson.objects.select_related(
        "child",
        "lesson",
        "enrolled_subject",
        "log",
    )

    if role == "student":
        child = getattr(user, "child_profile", None)
        if child is None:
            return ScheduledLesson.objects.none()
        return queryset.filter(child=child)

    if role == "parent":
        return queryset.filter(child__parent=user)

    if role == "teacher":
        return queryset.filter(
            child__course_enrollments__course__parent=user,
            child__course_enrollments__status="active",
        ).distinct()

    return ScheduledLesson.objects.none()


def _home_next_url(request, assignment=None):
    """Return safe redirect URL back to Home dashboard with selection context."""
    next_url = (request.POST.get("next") or "").strip()
    if next_url.startswith("/"):
        return next_url

    base = reverse("tracker:home_assignments")
    if assignment is None:
        return base
    return f"{base}?selected={assignment.pk}"


def _can_grade_assignment(user):
    role = getattr(getattr(user, "profile", None), "role", None)
    return role in {"parent", "teacher"}


def _can_submit_assignment(user, assignment):
    role = getattr(getattr(user, "profile", None), "role", None)
    if role != "student":
        return False
    child = getattr(user, "child_profile", None)
    return child is not None and assignment.enrollment.child_id == child.pk


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

    selected_lesson_log = getattr(selected_lesson, "log", None) if selected_lesson else None
    selected_lesson_comments = []
    selected_lesson_evidence_files = []
    selected_lesson_receipt_url = ""
    if selected_lesson is not None:
        selected_lesson_comments = list(
            selected_lesson.comments.select_related("author").order_by("-created_at")[:5]
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

    current_total_count = lesson_total_count if active_tab == "lessons" else assignment_total_count
    current_filtered_count = len(lessons) if active_tab == "lessons" else len(assignments)

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
                "plan_item__template",
                "plan_item__template__assignment_type",
            )
            .order_by("due_date", "id")
        )
        for assignment in assignment_qs:
            assignment.effective_status = _effective_assignment_status(
                assignment, today=today, viewer_role=viewer_role
            )
            assignments_by_date.setdefault(assignment.due_date, []).append(assignment)

    days = {}
    for i in range(6):
        date = start_date + datetime.timedelta(days=i)
        day_key = date.strftime("%A").lower()
        days[day_key] = {
            "date": date,
            "lessons": lesson_by_date.get(date, []),
            "vacations": vacations_by_date.get(date, []),
            "assignments": assignments_by_date.get(date, []),
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


def _can_access_student_assignment(user, assignment):
    """Return True when user is parent of child or the student owner."""
    profile = getattr(user, "profile", None)
    if profile is None:
        return False

    if profile.role in {"parent", "teacher"}:
        return assignment.enrollment.course.parent_id == user.pk

    if profile.role == "student":
        child = getattr(user, "child_profile", None)
        return child is not None and assignment.enrollment.child_id == child.pk

    return False


def _can_access_student_lesson(user, scheduled_lesson):
    """Return True when user is parent of child or the student owner."""
    profile = getattr(user, "profile", None)
    if profile is None:
        return False

    if profile.role == "parent":
        return scheduled_lesson.child.parent_id == user.pk

    if profile.role == "student":
        child = getattr(user, "child_profile", None)
        return child is not None and scheduled_lesson.child_id == child.pk

    return False


def _effective_lesson_status(log, scheduled_date, today=None):
    """Return UI-facing status for a lesson card/modal."""
    if today is None:
        today = datetime.date.today()

    if log and log.status == "complete":
        return "complete"
    if log and log.status == "overdue":
        return "overdue"
    if log and log.status == "skipped":
        return "skipped"
    if scheduled_date < today:
        return "overdue"
    return "incomplete"


def _lesson_status_meta(status_key):
    """Map lesson status key to UI label/icon metadata."""
    status_map = {
        "complete": {"label": "Complete", "icon": "check-circle-fill", "tone": "success"},
        "overdue": {"label": "Overdue", "icon": "exclamation-triangle-fill", "tone": "danger"},
        "incomplete": {"label": "Incomplete", "icon": "dash-circle", "tone": "secondary"},
        "skipped": {"label": "Skipped", "icon": "skip-forward-circle", "tone": "dark"},
    }
    return status_map.get(status_key, status_map["incomplete"])


def _parse_receipt_metadata(receipt_url):
    """Extract lightweight preview metadata from a completion receipt URL."""
    parsed = urlparse(receipt_url)
    path_parts = [p for p in parsed.path.split("/") if p]
    lesson_slug = ""
    result_token = ""

    if "lessons" in path_parts:
        lesson_idx = path_parts.index("lessons")
        if len(path_parts) > lesson_idx + 1:
            lesson_slug = path_parts[lesson_idx + 1]
    if "results" in path_parts:
        result_idx = path_parts.index("results")
        if len(path_parts) > result_idx + 1:
            result_token = path_parts[result_idx + 1]

    title = ""
    if lesson_slug:
        title = unquote(lesson_slug).replace("-", " ").strip().title()

    return {
        "provider": parsed.netloc,
        "path": parsed.path,
        "lesson_title_guess": title,
        "result_token": result_token,
        "shared": parsed.path.rstrip("/").endswith("/share"),
    }


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
        return JsonResponse({"error": "forbidden"}, status=403)

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


@login_required
def lesson_detail_view(request, scheduled_id):
    """Return JSON details for a single scheduled lesson.

    Ownership check: the lesson must belong to the student's child profile.
    """
    sl = get_object_or_404(ScheduledLesson, pk=scheduled_id)

    if not _can_access_student_lesson(request.user, sl):
        return JsonResponse({"error": "forbidden"}, status=403)

    log = getattr(sl, "log", None)
    status_key = _effective_lesson_status(log, sl.scheduled_date)
    status_meta = _lesson_status_meta(status_key)
    evidence_count = log.evidence_files.count() if log else 0
    evidence_files = (
        [
            {
                "id": ef.pk,
                "filename": ef.original_filename,
                "uploaded_at": ef.uploaded_at.strftime("%d %b %Y"),
            }
            for ef in log.evidence_files.all()
        ]
        if log
        else []
    )
    comments = list(sl.comments.select_related("author").all())
    iso = sl.scheduled_date.isocalendar()
    child_avatar = sl.child.photo.url if getattr(sl.child, "photo", None) else ""
    receipt_meta = log.completion_receipt_meta if log else {}

    return JsonResponse(
        {
            "id": sl.pk,
            "lesson_title": sl.lesson.lesson_title,
            "unit_title": sl.lesson.unit_title,
            "subject_name": sl.enrolled_subject.subject_name,
            "scheduled_date": sl.scheduled_date.strftime("%d %b %Y"),
            "scheduled_date_iso": sl.scheduled_date.isoformat(),
            "week_number": iso.week,
            "day_number": iso.weekday,
            "lesson_url": sl.lesson.lesson_url,
            "colour_hex": sl.enrolled_subject.colour_hex,
            "status": status_key,
            "status_label": status_meta["label"],
            "status_icon": status_meta["icon"],
            "status_tone": status_meta["tone"],
            "mastery": log.mastery if log else "unset",
            "student_notes": log.student_notes if log else "",
            "student_name": sl.child.first_name,
            "student_avatar": child_avatar,
            "completion_receipt_url": log.completion_receipt_url if log else "",
            "completion_receipt_meta": receipt_meta,
            "evidence_count": evidence_count,
            "evidence_files": evidence_files,
            "submissions_count": evidence_count,
            "comments": [
                {
                    "id": comment.pk,
                    "author": comment.author.get_username(),
                    "body": comment.body,
                    "created_at": timezone.localtime(comment.created_at).strftime("%d %b %Y, %H:%M"),
                }
                for comment in comments
            ],
            "comments_count": len(comments),
        }
    )


@login_required
@require_POST
def update_lesson_status_view(request, scheduled_id):
    """Accept a POST lesson status and persist it to LessonLog.

    Ownership is verified: the lesson must belong to the authenticated
    student's child profile.  Returns JSON on both success and error.
    """
    sl = get_object_or_404(ScheduledLesson, pk=scheduled_id)

    if not _can_access_student_lesson(request.user, sl):
        return JsonResponse({"error": "forbidden"}, status=403)

    new_status = request.POST.get("status", "")
    if new_status not in ("complete", "overdue", "skipped", "pending"):
        return JsonResponse({"error": "invalid status"}, status=400)

    log, _ = LessonLog.objects.get_or_create(scheduled_lesson=sl)
    log.status = new_status
    if new_status == "complete":
        log.completed_at = timezone.now()
    else:
        log.completed_at = None
    log.save()

    message_map = {
        "complete": "Lesson marked as complete.",
        "overdue": "Lesson marked as overdue.",
        "skipped": "Lesson skipped.",
        "pending": "Lesson marked as pending.",
    }

    return JsonResponse(
        {
            "success": True,
            "status": log.status,
            "message": message_map.get(new_status, "Lesson status updated."),
        }
    )


@login_required
@require_POST
def update_mastery_view(request, scheduled_id):
    """Accept a POST {mastery: 'green'|'amber'|'red'} and persist it to LessonLog.

    Ownership is verified: the lesson must belong to the authenticated
    student's child profile.  Returns JSON on both success and error.
    """
    sl = get_object_or_404(ScheduledLesson, pk=scheduled_id)

    if not _can_access_student_lesson(request.user, sl):
        return JsonResponse({"error": "forbidden"}, status=403)

    new_mastery = request.POST.get("mastery", "")
    if new_mastery not in ("green", "amber", "red"):
        return JsonResponse({"error": "invalid mastery"}, status=400)

    log, _ = LessonLog.objects.get_or_create(scheduled_lesson=sl)
    log.mastery = new_mastery
    log.save()

    return JsonResponse(
        {
            "success": True,
            "mastery": log.mastery,
        }
    )


@login_required
@require_POST
def save_notes_view(request, scheduled_id):
    """Accept a POST {notes: string} and persist it to LessonLog.student_notes.

    Ownership is verified: the lesson must belong to the authenticated
    student's child profile.  Notes are capped at 1000 characters.
    Returns JSON on both success and error.
    """
    sl = get_object_or_404(ScheduledLesson, pk=scheduled_id)

    if not _can_access_student_lesson(request.user, sl):
        return JsonResponse({"error": "forbidden"}, status=403)

    notes = request.POST.get("notes", "")
    if len(notes) > 1000:
        return JsonResponse({"error": "notes too long"}, status=400)

    log, _ = LessonLog.objects.get_or_create(scheduled_lesson=sl)
    log.student_notes = notes
    log.save()

    return JsonResponse({"success": True, "student_notes": log.student_notes})


@login_required
@require_POST
def reschedule_lesson_view(request, scheduled_id):
    """Accept a POST {new_date: 'YYYY-MM-DD'} and move the lesson to that date.

    Ownership is verified.  new_date must be strictly in the future (> today).
    Updates ScheduledLesson.scheduled_date and LessonLog.rescheduled_to.
    Returns JSON on both success and error.
    """
    sl = get_object_or_404(ScheduledLesson, pk=scheduled_id)

    if not _can_access_student_lesson(request.user, sl):
        return JsonResponse({"error": "forbidden"}, status=403)

    raw_date = request.POST.get("new_date", "").strip()
    try:
        new_date = datetime.date.fromisoformat(raw_date)
    except ValueError:
        return JsonResponse({"error": "invalid date"}, status=400)

    if new_date <= datetime.date.today():
        return JsonResponse({"error": "date must be in the future"}, status=400)

    sl.scheduled_date = new_date
    sl.save()

    log, _ = LessonLog.objects.get_or_create(scheduled_lesson=sl)
    log.rescheduled_to = new_date
    log.save()

    return JsonResponse({"success": True, "new_date": new_date.isoformat()})


@login_required
@require_POST
def save_receipt_link_view(request, scheduled_id):
    """Save a completion receipt URL and lightweight parsed metadata."""
    sl = get_object_or_404(ScheduledLesson, pk=scheduled_id)

    if not _can_access_student_lesson(request.user, sl):
        return JsonResponse({"error": "forbidden"}, status=403)

    receipt_url = (request.POST.get("receipt_url") or "").strip()
    meta = {}
    if receipt_url:
        parsed = urlparse(receipt_url)
        if not parsed.scheme or not parsed.netloc:
            return JsonResponse({"error": "invalid receipt url"}, status=400)
        meta = _parse_receipt_metadata(receipt_url)

    log, _ = LessonLog.objects.get_or_create(scheduled_lesson=sl)
    log.completion_receipt_url = receipt_url
    log.completion_receipt_meta = meta
    log.save(update_fields=["completion_receipt_url", "completion_receipt_meta"])

    return JsonResponse(
        {
            "success": True,
            "completion_receipt_url": log.completion_receipt_url,
            "completion_receipt_meta": log.completion_receipt_meta,
        }
    )


@login_required
@require_POST
def add_lesson_comment_view(request, scheduled_id):
    """Create a lesson comment for parent/student journal discussion."""
    sl = get_object_or_404(ScheduledLesson, pk=scheduled_id)

    if not _can_access_student_lesson(request.user, sl):
        return JsonResponse({"error": "forbidden"}, status=403)

    body = (request.POST.get("body") or "").strip()
    if not body:
        return JsonResponse({"error": "comment required"}, status=400)
    if len(body) > 2000:
        return JsonResponse({"error": "comment too long"}, status=400)

    comment = LessonComment.objects.create(
        scheduled_lesson=sl,
        author=request.user,
        body=body,
    )

    return JsonResponse(
        {
            "success": True,
            "comment": {
                "id": comment.pk,
                "author": comment.author.get_username(),
                "body": comment.body,
                "created_at": timezone.localtime(comment.created_at).strftime("%d %b %Y, %H:%M"),
            },
            "comments_count": sl.comments.count(),
        }
    )


@login_required
@require_POST
def edit_scheduled_lesson_view(request, scheduled_id):
    """Edit scheduled lesson date and optional order on day."""
    sl = get_object_or_404(ScheduledLesson, pk=scheduled_id)

    if not _can_access_student_lesson(request.user, sl):
        return JsonResponse({"error": "forbidden"}, status=403)

    raw_date = (request.POST.get("scheduled_date") or "").strip()
    if not raw_date:
        return JsonResponse({"error": "scheduled_date required"}, status=400)
    try:
        new_date = datetime.date.fromisoformat(raw_date)
    except ValueError:
        return JsonResponse({"error": "invalid date"}, status=400)

    raw_order = (request.POST.get("order_on_day") or "").strip()
    if raw_order:
        try:
            sl.order_on_day = max(0, int(raw_order))
        except ValueError:
            return JsonResponse({"error": "invalid order"}, status=400)

    sl.scheduled_date = new_date
    sl.save(update_fields=["scheduled_date", "order_on_day"])
    return JsonResponse(
        {
            "success": True,
            "scheduled_date": sl.scheduled_date.isoformat(),
            "order_on_day": sl.order_on_day,
        }
    )


@login_required
@require_POST
def delete_scheduled_lesson_view(request, scheduled_id):
    """Delete a scheduled lesson entry from the calendar."""
    sl = get_object_or_404(ScheduledLesson, pk=scheduled_id)

    if not _can_access_student_lesson(request.user, sl):
        return JsonResponse({"error": "forbidden"}, status=403)

    sl.delete()
    return JsonResponse({"success": True})


_ALLOWED_EVIDENCE_TYPES = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
        "image/svg+xml",
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
)


@login_required
@require_POST
def upload_evidence_view(request, scheduled_id):
    """Accept a multipart POST with a 'file' field and store it on Cloudinary.

    Validates ownership and restricts uploads to images, PDF, .doc, .docx.
    Creates a LessonLog if one does not yet exist.
    Returns JSON: {success, file_id, filename, uploaded_at}.
    """
    sl = get_object_or_404(ScheduledLesson, pk=scheduled_id)

    if not _can_access_student_lesson(request.user, sl):
        return JsonResponse({"error": "forbidden"}, status=403)

    uploaded_file = request.FILES.get("file")
    if not uploaded_file:
        return JsonResponse({"error": "no file provided"}, status=400)

    content_type = (uploaded_file.content_type or "").split(";")[0].strip().lower()
    if not (
        content_type.startswith("image/") or content_type in _ALLOWED_EVIDENCE_TYPES
    ):
        return JsonResponse({"error": "invalid file type"}, status=400)

    log, _ = LessonLog.objects.get_or_create(scheduled_lesson=sl)
    try:
        evidence = EvidenceFile.objects.create(
            lesson_log=log,
            file=uploaded_file,
            original_filename=uploaded_file.name,
            uploaded_by=request.user,
        )
    except Exception as exc:
        return JsonResponse(
            {"success": False, "error": f"Upload failed: {exc}"}, status=500
        )

    return JsonResponse(
        {
            "success": True,
            "file_id": evidence.pk,
            "filename": evidence.original_filename,
            "uploaded_at": evidence.uploaded_at.strftime("%d %b %Y"),
            "evidence_count": log.evidence_files.count(),
        }
    )


@login_required
@require_POST
def delete_evidence_view(request, file_id):
    """Delete an evidence file from Cloudinary and the database.

    Only the student who uploaded the file may delete it.
    Returns JSON: {success, evidence_count}.
    """
    import cloudinary.uploader

    evidence = get_object_or_404(EvidenceFile, pk=file_id)
    sl = evidence.lesson_log.scheduled_lesson
    if not _can_access_student_lesson(request.user, sl):
        return JsonResponse({"error": "forbidden"}, status=403)

    public_id = (
        evidence.file.public_id
        if hasattr(evidence.file, "public_id")
        else str(evidence.file)
    )
    try:
        cloudinary.uploader.destroy(public_id, resource_type="raw")
    except Exception:
        pass  # best-effort; always delete DB record

    log = evidence.lesson_log
    evidence.delete()

    return JsonResponse(
        {
            "success": True,
            "evidence_count": log.evidence_files.count(),
        }
    )


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
