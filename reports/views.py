import datetime
import io
from collections import defaultdict
from decimal import Decimal, InvalidOperation

import cloudinary.utils
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import models
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from xhtml2pdf import pisa

from accounts.decorators import role_required
from courses.models import CourseEnrollment
from planning.models import (
    AssignmentAttachment,
    AssignmentComment,
    AssignmentSubmission,
    StudentAssignment,
)
from reports.models import Report
from reports.services_gradebook import (
    get_assignment_percent,
    lazy_backfill_enrollment_grade_summary,
    recalculate_enrollment_grade,
)
from scheduler.models import Child
from tracker.models import LessonLog
from tracker.views.utils import _hydrate_assignment_display

from .forms import ReportForm
from .services import generate_pdf


def _user_role(user):
    return getattr(getattr(user, "profile", None), "role", None)


def _is_gradebook_owner_role(role):
    return role in {"parent", "teacher"}


def _can_submit_assignment(user, assignment):
    if _user_role(user) != "student":
        return False
    child = getattr(user, "child_profile", None)
    return child is not None and assignment.enrollment.child_id == child.pk


def _assignment_next_url(request, assignment):
    next_url = (request.POST.get("next") or "").strip()
    if next_url.startswith("/"):
        return next_url
    return reverse("reports:gradebook_detail", args=[assignment.enrollment_id])


@login_required
@role_required("parent")
def create_report_view(request, child_id):
    """Show and process the report creation form.

    GET: renders the form with a lesson-count preview for the child.
    POST: validates the form; on success generates a PDF, saves the report,
    and redirects to the report detail page.
    """
    child = get_object_or_404(Child, pk=child_id, parent=request.user)

    form = ReportForm(request.POST or None)
    preview_count = None

    if request.method == "POST" and form.is_valid():
        report = form.save(commit=False)
        report.child = child
        report.created_by = request.user
        report.save()
        generate_pdf(report)
        messages.success(request, "Report generated! Download below.")
        return redirect("reports:report_detail", pk=report.pk)

    completed_count = LessonLog.objects.filter(
        scheduled_lesson__child=child,
        status="complete",
    ).count()

    return render(
        request,
        "reports/create_report.html",
        {
            "form": form,
            "child": child,
            "preview_count": preview_count,
            "total_completed": completed_count,
        },
    )


@login_required
@role_required("parent")
def report_detail_view(request, pk):
    """Display report metadata, PDF download link, and share token URL."""
    report = get_object_or_404(Report, pk=pk, child__parent=request.user)

    download_url = None
    if report.pdf_file:
        download_url, _ = cloudinary.utils.cloudinary_url(
            str(report.pdf_file),
            resource_type="raw",
            format="pdf",
        )

    share_url = request.build_absolute_uri(
        reverse("reports:shared_report", kwargs={"token": report.share_token})
    )

    return render(
        request,
        "reports/report_detail.html",
        {
            "report": report,
            "download_url": download_url,
            "share_url": share_url,
        },
    )


def token_report_view(request, token):
    """Public read-only report view accessible via a secure UUID token."""
    report = get_object_or_404(Report, share_token=token)

    if report.token_expires_at and report.token_expires_at <= timezone.now():
        return HttpResponseForbidden("This link has expired")

    return render(
        request,
        "reports/shared_report.html",
        {
            "report": report,
        },
    )


@login_required
def gradebook_list_view(request):
    """Role-aware gradebook index grouped by student."""
    role = _user_role(request.user)
    if role not in {"parent", "teacher", "student"}:
        return HttpResponseForbidden()

    tab = request.GET.get("tab", "current")
    if tab not in {"current", "completed"}:
        tab = "current"

    status_filter = "completed" if tab == "completed" else "active"
    enrollment_qs = CourseEnrollment.objects.select_related("child", "course").filter(
        status=status_filter
    )
    if _is_gradebook_owner_role(role):
        enrollment_qs = enrollment_qs.filter(course__parent=request.user)
    else:
        child = getattr(request.user, "child_profile", None)
        if child is None:
            enrollment_qs = CourseEnrollment.objects.none()
        else:
            enrollment_qs = enrollment_qs.filter(child=child)

    enrollments = list(enrollment_qs.order_by("child__first_name", "course__name"))

    by_child = {}
    for enrollment in enrollments:
        summary = lazy_backfill_enrollment_grade_summary(enrollment)
        row = {
            "enrollment": enrollment,
            "summary": summary,
        }
        by_child.setdefault(enrollment.child, []).append(row)

    children_rows = [
        {
            "child": child,
            "enrollments": rows,
        }
        for child, rows in by_child.items()
    ]

    return render(
        request,
        "reports/gradebook_list.html",
        {
            "tab": tab,
            "children_rows": children_rows,
            "can_export": _is_gradebook_owner_role(role),
            "user_role": role,
        },
    )


@login_required
def gradebook_detail_view(request, enrollment_id):
    """Gradebook details for one enrollment with modal grading updates."""
    role = _user_role(request.user)
    if role not in {"parent", "teacher", "student"}:
        return HttpResponseForbidden()

    enrollment_qs = CourseEnrollment.objects.select_related("course", "child").filter(
        pk=enrollment_id
    )
    if _is_gradebook_owner_role(role):
        enrollment_qs = enrollment_qs.filter(course__parent=request.user)
    else:
        child = getattr(request.user, "child_profile", None)
        if child is None:
            return HttpResponseForbidden()
        enrollment_qs = enrollment_qs.filter(child=child)

    enrollment = get_object_or_404(enrollment_qs)

    if request.method == "POST":
        if not _is_gradebook_owner_role(role):
            return HttpResponseForbidden()

        action = request.POST.get("action", "save_grade")
        assignment_id = request.POST.get("assignment_id")
        assignment = get_object_or_404(
            StudentAssignment,
            pk=assignment_id,
            enrollment=enrollment,
        )

        update_fields = []

        def _parse_decimal(raw_value):
            if raw_value == "":
                return None
            try:
                return Decimal(raw_value)
            except (InvalidOperation, TypeError, ValueError):
                return None

        score_raw = (request.POST.get("score") or "").strip()
        points_raw = (request.POST.get("points_available") or "").strip()
        percent_raw = (request.POST.get("score_percent") or "").strip()
        status_raw = (request.POST.get("status") or "").strip()
        due_date_raw = (request.POST.get("due_date") or "").strip()
        notes_raw = request.POST.get("grading_notes", "").strip()

        score_value = _parse_decimal(score_raw)
        points_value = _parse_decimal(points_raw)
        percent_value = _parse_decimal(percent_raw)

        assignment.score = score_value
        assignment.points_available = points_value
        assignment.score_percent = percent_value
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

        if action == "save_modal":
            if status_raw in {
                "pending",
                "complete",
                "overdue",
                "needs_grading",
            }:
                assignment.status = status_raw
                update_fields.append("status")

            if (
                assignment.status in {"complete", "needs_grading"}
                and assignment.completed_at is None
            ):
                assignment.completed_at = timezone.now()
                update_fields.append("completed_at")
            if (
                assignment.status not in {"complete", "needs_grading"}
                and assignment.completed_at is not None
            ):
                assignment.completed_at = None
                update_fields.append("completed_at")

            if due_date_raw:
                try:
                    due_date = datetime.date.fromisoformat(due_date_raw)
                except ValueError:
                    due_date = None
                if due_date is not None:
                    assignment.due_date = due_date
                    update_fields.append("due_date")

        has_grading_input = any([score_raw, points_raw, percent_raw, notes_raw])
        if has_grading_input:
            assignment.status = "complete"
            assignment.completed_at = assignment.completed_at or timezone.now()
            update_fields.extend(["status", "completed_at"])

        assignment.save(update_fields=sorted(set(update_fields)))
        recalculate_enrollment_grade(enrollment)
        messages.success(request, "Grade saved.")
        return redirect(
            "reports:gradebook_detail",
            enrollment_id=enrollment.id,
        )

    assignments = list(
        enrollment.assignments.select_related(
            "new_plan_item__assignment_detail__assignment_type"
        ).order_by("due_date", "id")
    )
    assignment_ids = [assignment.id for assignment in assignments]

    # Note: AssignmentAttachment still uses old plan_item FK during transition
    old_plan_item_ids = [assignment.plan_item_id for assignment in assignments]
    attachments_by_plan_item = defaultdict(list)
    for attachment in AssignmentAttachment.objects.filter(
        plan_item_id__in=old_plan_item_ids
    ).order_by("created_at"):
        attachments_by_plan_item[attachment.plan_item_id].append(attachment)

    comments_by_assignment = defaultdict(list)
    for comment in (
        AssignmentComment.objects.filter(assignment_id__in=assignment_ids)
        .select_related("author")
        .order_by("created_at")
    ):
        comments_by_assignment[comment.assignment_id].append(comment)

    submissions_by_assignment = defaultdict(list)
    for submission in (
        AssignmentSubmission.objects.filter(assignment_id__in=assignment_ids)
        .select_related("uploaded_by")
        .order_by("-created_at")
    ):
        submissions_by_assignment[submission.assignment_id].append(submission)

    today = timezone.localdate()
    for assignment in assignments:
        # Hydrate display fields for template rendering
        _hydrate_assignment_display(assignment)

        if assignment.status == "complete":
            assignment.display_status = "complete"
        elif assignment.status == "needs_grading":
            assignment.display_status = "needs_grading"
        elif assignment.due_date < today:
            assignment.display_status = "overdue"
        else:
            assignment.display_status = "pending"
        assignment.effective_percent = get_assignment_percent(assignment)
        # Build edit URL using new_plan_item for unified model
        plan_item_for_url = (
            assignment.new_plan_item_id
            if assignment.new_plan_item_id
            else assignment.plan_item_id
        )
        assignment.edit_url = (
            f"{reverse('planning:plan_course', args=[enrollment.course.id])}"
            f"?edit={plan_item_for_url}"
        )
        assignment.attachments_for_modal = attachments_by_plan_item.get(
            assignment.plan_item_id, []
        )
        assignment.comments_for_modal = comments_by_assignment.get(assignment.id, [])
        assignment.submissions_for_modal = submissions_by_assignment.get(
            assignment.id, []
        )
        assignment.attachments_count = len(assignment.attachments_for_modal)
        assignment.comments_count = len(assignment.comments_for_modal)
        assignment.submissions_count = len(assignment.submissions_for_modal)
        assignment.status_action_url = reverse(
            "reports:gradebook_assignment_status",
            kwargs={"assignment_id": assignment.id},
        )
        assignment.comment_action_url = reverse(
            "reports:gradebook_assignment_comment_create",
            kwargs={"assignment_id": assignment.id},
        )
        assignment.submission_action_url = reverse(
            "reports:gradebook_assignment_submission_upload",
            kwargs={"assignment_id": assignment.id},
        )
        assignment.can_submit = _can_submit_assignment(request.user, assignment)

    sort_by = request.GET.get("sort", "due")
    sort_order = request.GET.get("order", "asc")
    if sort_by not in {"due", "status", "type", "name", "percent"}:
        sort_by = "due"
    if sort_order not in {"asc", "desc"}:
        sort_order = "asc"

    def _assignment_sort_name(item):
        plan_item = getattr(item, "new_plan_item", None)
        if plan_item:
            return plan_item.name.lower()
        legacy_plan_item = getattr(item, "plan_item", None)
        if legacy_plan_item and getattr(legacy_plan_item, "template", None):
            return legacy_plan_item.template.name.lower()
        return ""

    def _assignment_sort_type(item):
        plan_item = getattr(item, "new_plan_item", None)
        if plan_item:
            detail = getattr(plan_item, "assignment_detail", None)
            assignment_type = getattr(detail, "assignment_type", None)
            if assignment_type:
                return assignment_type.name.lower()
        legacy_plan_item = getattr(item, "plan_item", None)
        if legacy_plan_item and getattr(legacy_plan_item, "template", None):
            assignment_type = getattr(
                legacy_plan_item.template, "assignment_type", None
            )
            if assignment_type:
                return assignment_type.name.lower()
        return ""

    if sort_by == "status":
        status_rank = {
            "pending": 0,
            "overdue": 1,
            "needs_grading": 2,
            "complete": 3,
        }

        assignments.sort(
            key=lambda item: (
                status_rank.get(item.display_status, 99),
                item.due_date,
            )
        )
    elif sort_by == "type":
        assignments.sort(key=lambda item: (_assignment_sort_type(item), item.due_date))
    elif sort_by == "name":
        assignments.sort(key=lambda item: (_assignment_sort_name(item), item.due_date))
    elif sort_by == "percent":
        assignments.sort(
            key=lambda item: (
                Decimal(item.effective_percent),
                item.due_date,
            )
        )
    else:
        assignments.sort(key=lambda item: (item.due_date, item.id))

    if sort_order == "desc":
        assignments.reverse()

    summary = lazy_backfill_enrollment_grade_summary(enrollment)
    progress_done = len(
        [
            assignment
            for assignment in assignments
            if assignment.status in {"complete", "needs_grading"}
        ]
    )
    progress_total = len(assignments)
    progress_percent = (
        int((progress_done / progress_total) * 100) if progress_total else 0
    )

    return render(
        request,
        "reports/gradebook_detail.html",
        {
            "enrollment": enrollment,
            "summary": summary,
            "assignments": assignments,
            "sort_by": sort_by,
            "sort_order": sort_order,
            "user_role": role,
            "can_grade": _is_gradebook_owner_role(role),
            "can_respond": role in {"parent", "teacher", "student"},
            "progress_done": progress_done,
            "progress_total": progress_total,
            "progress_percent": progress_percent,
            "next_url": request.get_full_path(),
        },
    )


@login_required
@require_POST
def gradebook_assignment_status_view(request, assignment_id):
    assignment = get_object_or_404(
        StudentAssignment.objects.select_related(
            "enrollment__course", "enrollment__child"
        ),
        pk=assignment_id,
    )
    role = _user_role(request.user)

    if role == "student":
        child = getattr(request.user, "child_profile", None)
        if child is None or assignment.enrollment.child_id != child.pk:
            return HttpResponseForbidden()
    elif _is_gradebook_owner_role(role):
        if assignment.enrollment.course.parent_id != request.user.pk:
            return HttpResponseForbidden()
    else:
        return HttpResponseForbidden()

    requested = (request.POST.get("status") or "").strip().lower()
    if requested not in {"done", "incomplete"}:
        return redirect(_assignment_next_url(request, assignment))

    if requested == "done":
        assignment.status = "needs_grading" if role == "student" else "complete"
        assignment.completed_at = timezone.now()
    else:
        assignment.status = "pending"
        assignment.completed_at = None

    assignment.save(update_fields=["status", "completed_at"])
    recalculate_enrollment_grade(assignment.enrollment)
    return redirect(_assignment_next_url(request, assignment))


@login_required
@require_POST
def gradebook_assignment_comment_create_view(request, assignment_id):
    assignment = get_object_or_404(
        StudentAssignment.objects.select_related(
            "enrollment__course", "enrollment__child"
        ),
        pk=assignment_id,
    )
    role = _user_role(request.user)

    if role == "student":
        child = getattr(request.user, "child_profile", None)
        if child is None or assignment.enrollment.child_id != child.pk:
            return HttpResponseForbidden()
    elif _is_gradebook_owner_role(role):
        if assignment.enrollment.course.parent_id != request.user.pk:
            return HttpResponseForbidden()
    else:
        return HttpResponseForbidden()

    body = (request.POST.get("comment") or "").strip()
    if body:
        AssignmentComment.objects.create(
            assignment=assignment,
            author=request.user,
            body=body,
        )
    return redirect(_assignment_next_url(request, assignment))


@login_required
@require_POST
def gradebook_assignment_submission_upload_view(request, assignment_id):
    assignment = get_object_or_404(
        StudentAssignment.objects.select_related(
            "enrollment__course", "enrollment__child"
        ),
        pk=assignment_id,
    )

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
    return redirect(_assignment_next_url(request, assignment))


@login_required
@role_required("parent")
def gradebook_transcript_view(request, child_id):
    """Transcript-style gradebook output for one child."""
    child = get_object_or_404(Child, pk=child_id, parent=request.user)

    enrollments = list(
        CourseEnrollment.objects.select_related("course", "child")
        .filter(course__parent=request.user, child=child)
        .order_by("course__name")
    )

    transcript_rows = []
    all_assignment_rows = []
    total_credits = Decimal("0")
    weighted_gpa_sum = Decimal("0")
    weighted_percent_sum = Decimal("0")
    total_missing = 0
    total_late = 0

    for enrollment in enrollments:
        summary = lazy_backfill_enrollment_grade_summary(enrollment)
        if summary is None:
            continue

        credits = enrollment.course.credits or Decimal("1.0")
        credits = Decimal(str(credits))
        total_credits += credits

        gpa_points = summary.gpa_points or Decimal("0")
        final_percent = summary.final_percent or Decimal("0")
        weighted_gpa_sum += Decimal(str(gpa_points)) * credits
        weighted_percent_sum += Decimal(str(final_percent)) * credits
        total_missing += summary.missing_assignments_count
        total_late += summary.late_assignments_count

        transcript_rows.append(
            {
                "enrollment": enrollment,
                "summary": summary,
                "credits": credits,
            }
        )

        assignment_qs = enrollment.assignments.select_related(
            "new_plan_item__assignment_detail__assignment_type"
        ).order_by("due_date", "id")
        for assignment in assignment_qs:
            assignment_name = ""
            assignment_type_name = ""
            plan_item = getattr(assignment, "new_plan_item", None)
            if plan_item:
                assignment_name = plan_item.name
                detail = getattr(plan_item, "assignment_detail", None)
                if detail and detail.assignment_type:
                    assignment_type_name = detail.assignment_type.name

            all_assignment_rows.append(
                {
                    "course": enrollment.course.name,
                    "name": assignment_name,
                    "type": assignment_type_name,
                    "due_date": assignment.due_date,
                    "status": assignment.status,
                    "score": assignment.score,
                    "points_available": assignment.points_available,
                    "percent": get_assignment_percent(assignment),
                }
            )

    overall_gpa = Decimal("0")
    overall_percent = Decimal("0")
    if total_credits > 0:
        overall_gpa = (weighted_gpa_sum / total_credits).quantize(Decimal("0.01"))
        overall_percent = (weighted_percent_sum / total_credits).quantize(
            Decimal("0.01")
        )

    context = {
        "child": child,
        "transcript_rows": transcript_rows,
        "assignment_rows": all_assignment_rows,
        "overall_gpa": overall_gpa,
        "overall_percent": overall_percent,
        "total_missing": total_missing,
        "total_late": total_late,
    }

    if request.GET.get("format") == "pdf":
        html = render_to_string(
            "reports/gradebook_transcript_pdf.html",
            context,
        )
        pdf_buffer = io.BytesIO()
        pisa.CreatePDF(html, dest=pdf_buffer)
        pdf_buffer.seek(0)

        filename = f"transcript_{child.first_name}_{timezone.now().date()}".replace(
            " ", "_"
        )
        response = HttpResponse(
            pdf_buffer.read(),
            content_type="application/pdf",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}.pdf"'
        return response

    return render(request, "reports/gradebook_transcript.html", context)


# ── Tracking overview ───────────────────────────────────────────────────────


@role_required("parent")
def tracking_overview_view(request):
    """MVP tracking dashboard: lesson/assignment/activity completion per course."""
    from courses.models import Course
    from planning.models import ActivityProgress, StudentAssignment
    from scheduler.models import ScheduledLesson

    courses = list(
        Course.objects.filter(parent=request.user, is_archived=False)
        .prefetch_related("enrollments__child", "subject_configs")
        .order_by("name")
    )

    course_summaries = []
    for course in courses:
        active_enrollments = [
            e for e in course.enrollments.all() if e.status == "active"
        ]
        course_lesson_qs = ScheduledLesson.objects.filter(
            models.Q(plan_item__course=course) | models.Q(course_subject__course=course)
        ).distinct()

        # Lessons: ScheduledLesson with LessonLog.status=complete
        total_lessons = course_lesson_qs.count()
        complete_lessons = course_lesson_qs.filter(log__status="complete").count()

        # Assignments: StudentAssignment complete vs total
        total_assignments = StudentAssignment.objects.filter(
            enrollment__course=course
        ).count()
        complete_assignments = StudentAssignment.objects.filter(
            enrollment__course=course, status__in=["complete", "needs_grading"]
        ).count()

        # Activities: ActivityProgress complete vs total
        total_activities = ActivityProgress.objects.filter(
            enrollment__course=course
        ).count()
        complete_activities = ActivityProgress.objects.filter(
            enrollment__course=course, status="complete"
        ).count()

        # Per-subject breakdown (CourseSubjectConfig)
        subject_rows = []
        for sc in course.subject_configs.filter(is_active=True):
            s_total = course_lesson_qs.filter(course_subject=sc).count()
            s_complete = course_lesson_qs.filter(
                course_subject=sc,
                log__status="complete",
            ).count()
            subject_rows.append(
                {
                    "subject_name": sc.subject_name,
                    "total": s_total,
                    "complete": s_complete,
                    "pct": round(s_complete / s_total * 100) if s_total else 0,
                }
            )

        course_summaries.append(
            {
                "course": course,
                "active_enrollment_count": len(active_enrollments),
                "total_lessons": total_lessons,
                "complete_lessons": complete_lessons,
                "lesson_pct": (
                    round(complete_lessons / total_lessons * 100)
                    if total_lessons
                    else 0
                ),
                "total_assignments": total_assignments,
                "complete_assignments": complete_assignments,
                "assignment_pct": (
                    round(complete_assignments / total_assignments * 100)
                    if total_assignments
                    else 0
                ),
                "total_activities": total_activities,
                "complete_activities": complete_activities,
                "activity_pct": (
                    round(complete_activities / total_activities * 100)
                    if total_activities
                    else 0
                ),
                "subject_rows": subject_rows,
            }
        )

    return render(
        request,
        "reports/tracking_overview.html",
        {
            "course_summaries": course_summaries,
        },
    )
