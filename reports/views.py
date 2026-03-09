from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import role_required
from scheduler.models import Child
from tracker.models import LessonLog

from .forms import ReportForm


@login_required
@role_required('parent')
def create_report_view(request, child_id):
    """Show and process the report creation form.

    GET: renders the form with a lesson-count preview for the child.
    POST: validates the form; on success redirects to a not-yet-implemented
    detail page (placeholder redirect back to dashboard until S3.2).
    """
    child = get_object_or_404(Child, pk=child_id, parent=request.user)

    form = ReportForm(request.POST or None)
    preview_count = None

    if request.method == 'POST' and form.is_valid():
        report = form.save(commit=False)
        report.child = child
        report.created_by = request.user
        report.save()
        return redirect('scheduler:parent_dashboard')

    # Preview: count completed lessons in the current date range
    if request.method == 'GET':
        # Show a preview when date params are passed as GET query strings
        # (used by JS to update the preview count without a full POST)
        pass

    # Count completed LessonLogs for this child (date range not yet set — shown after form entry)
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

