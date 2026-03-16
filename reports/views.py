import datetime
import io
from decimal import Decimal, InvalidOperation

import cloudinary.utils
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from xhtml2pdf import pisa

from accounts.decorators import role_required
from courses.models import CourseEnrollment
from planning.models import StudentAssignment
from reports.models import Report
from reports.services_gradebook import (
    get_assignment_percent,
    lazy_backfill_enrollment_grade_summary,
    recalculate_enrollment_grade,
)
from scheduler.models import Child
from tracker.models import LessonLog

from .forms import ReportForm
from .services import generate_pdf


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
@role_required("parent")
def gradebook_list_view(request):
    """Parent-facing gradebook index grouped by student."""
    tab = request.GET.get("tab", "current")
    if tab not in {"current", "completed"}:
        tab = "current"

    status_filter = "completed" if tab == "completed" else "active"
    enrollments = list(
        CourseEnrollment.objects.select_related("child", "course")
        .filter(course__parent=request.user, status=status_filter)
        .order_by("child__first_name", "course__name")
    )

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
        },
    )


@login_required
@role_required("parent")
def gradebook_detail_view(request, enrollment_id):
    """Gradebook details for one enrollment with modal grading updates."""
    enrollment = get_object_or_404(
        CourseEnrollment.objects.select_related("course", "child"),
        pk=enrollment_id,
        course__parent=request.user,
    )

    if request.method == "POST":
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

        score_value = _parse_decimal(score_raw)
        points_value = _parse_decimal(points_raw)
        percent_value = _parse_decimal(percent_raw)

        assignment.score = score_value
        assignment.points_available = points_value
        assignment.score_percent = percent_value
        assignment.grading_notes = request.POST.get("grading_notes", "").strip()
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
            if status_raw in {"pending", "complete", "overdue"}:
                assignment.status = status_raw
                update_fields.append("status")

            if assignment.status == "complete" and assignment.completed_at is None:
                assignment.completed_at = timezone.now()
                update_fields.append("completed_at")
            if assignment.status != "complete" and assignment.completed_at is not None:
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

        assignment.save(update_fields=sorted(set(update_fields)))
        recalculate_enrollment_grade(enrollment)
        messages.success(request, "Grade saved.")
        return redirect(
            "reports:gradebook_detail",
            enrollment_id=enrollment.id,
        )

    assignments = list(
        enrollment.assignments.select_related(
            "plan_item__template__assignment_type"
        ).order_by("due_date", "id")
    )
    today = timezone.localdate()
    for assignment in assignments:
        if assignment.status == "complete":
            assignment.display_status = "complete"
        elif assignment.due_date < today:
            assignment.display_status = "overdue"
        else:
            assignment.display_status = "pending"
        assignment.effective_percent = get_assignment_percent(assignment)
        assignment.edit_url = (
            f"{reverse('planning:plan_course', args=[enrollment.course.id])}"
            f"?edit={assignment.plan_item_id}"
        )

    sort_by = request.GET.get("sort", "due")
    sort_order = request.GET.get("order", "asc")
    if sort_by not in {"due", "status", "type", "name", "percent"}:
        sort_by = "due"
    if sort_order not in {"asc", "desc"}:
        sort_order = "asc"

    if sort_by == "status":
        status_rank = {"pending": 0, "overdue": 1, "complete": 2}
        assignments.sort(
            key=lambda item: (
                status_rank.get(item.display_status, 99),
                item.due_date,
            )
        )
    elif sort_by == "type":
        assignments.sort(
            key=lambda item: (
                item.plan_item.template.assignment_type.name.lower(),
                item.due_date,
            )
        )
    elif sort_by == "name":
        assignments.sort(
            key=lambda item: (
                item.plan_item.template.name.lower(),
                item.due_date,
            )
        )
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

    return render(
        request,
        "reports/gradebook_detail.html",
        {
            "enrollment": enrollment,
            "summary": summary,
            "assignments": assignments,
            "sort_by": sort_by,
            "sort_order": sort_order,
        },
    )


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
            "plan_item__template__assignment_type"
        ).order_by("due_date", "id")
        for assignment in assignment_qs:
            all_assignment_rows.append(
                {
                    "course": enrollment.course.name,
                    "name": assignment.plan_item.template.name,
                    "type": assignment.plan_item.template.assignment_type.name,
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
