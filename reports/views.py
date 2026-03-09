from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

import cloudinary.utils

from accounts.decorators import role_required
from reports.models import Report
from scheduler.models import Child
from tracker.models import LessonLog

from .forms import ReportForm
from .services import generate_pdf


@login_required
@role_required('parent')
def create_report_view(request, child_id):
    """Show and process the report creation form.

    GET: renders the form with a lesson-count preview for the child.
    POST: validates the form; on success generates a PDF, saves the report,
    and redirects to the report detail page.
    """
    child = get_object_or_404(Child, pk=child_id, parent=request.user)

    form = ReportForm(request.POST or None)
    preview_count = None

    if request.method == 'POST' and form.is_valid():
        report = form.save(commit=False)
        report.child = child
        report.created_by = request.user
        report.save()
        generate_pdf(report)
        messages.success(request, 'Report generated! Download below.')
        return redirect('reports:report_detail', pk=report.pk)

    completed_count = LessonLog.objects.filter(
        scheduled_lesson__child=child,
        status='complete',
    ).count()

    return render(request, 'reports/create_report.html', {
        'form': form,
        'child': child,
        'preview_count': preview_count,
        'total_completed': completed_count,
    })


@login_required
@role_required('parent')
def report_detail_view(request, pk):
    """Display report metadata, PDF download link, and share token URL."""
    report = get_object_or_404(Report, pk=pk, child__parent=request.user)

    download_url = None
    if report.pdf_file:
        download_url, _ = cloudinary.utils.cloudinary_url(
            str(report.pdf_file),
            resource_type='raw',
            format='pdf',
        )

    return render(request, 'reports/report_detail.html', {
        'report': report,
        'download_url': download_url,
    })

