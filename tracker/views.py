import datetime
import uuid

from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import role_required
from scheduler.models import ScheduledLesson, Vacation
from tracker.models import EvidenceFile, LessonLog


def _build_calendar_context(child, year, week, today, is_readonly, child_id=None, child_name=None):
    """Shared helper: build the full context dict for the calendar template.

    Covers Mon–Sat (6 days), queries lessons and vacations that overlap
    the week, and computes navigation years/weeks.
    """
    monday = datetime.date.fromisocalendar(year, week, 1)
    saturday = monday + datetime.timedelta(days=5)

    # Lessons
    lesson_by_date: dict = {}
    if child is not None:
        qs = (
            ScheduledLesson.objects
            .filter(child=child, scheduled_date__gte=monday, scheduled_date__lte=saturday)
            .select_related('lesson', 'enrolled_subject', 'log')
        )
        for sl in qs:
            lesson_by_date.setdefault(sl.scheduled_date, []).append(sl)

    # Vacations overlapping this week
    vacations_by_date: dict = {}
    if child is not None:
        vac_qs = Vacation.objects.filter(
            child=child,
            start_date__lte=saturday,
            end_date__gte=monday,
        )
        for vac in vac_qs:
            cur = max(vac.start_date, monday)
            end = min(vac.end_date, saturday)
            while cur <= end:
                vacations_by_date.setdefault(cur, []).append(vac)
                cur += datetime.timedelta(days=1)

    day_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday']
    days = {}
    for i, name in enumerate(day_names):
        date = monday + datetime.timedelta(days=i)
        days[name] = {
            'date': date,
            'lessons': lesson_by_date.get(date, []),
            'vacations': vacations_by_date.get(date, []),
        }

    # Week navigation
    prev_monday = monday - datetime.timedelta(weeks=1)
    next_monday = monday + datetime.timedelta(weeks=1)
    prev_y, prev_w, _ = prev_monday.isocalendar()
    next_y, next_w, _ = next_monday.isocalendar()
    today_iso = today.isocalendar()

    # Header date range e.g. "Mar 09, 2026 — Mar 15, 2026"
    week_display = f"{monday.strftime('%b %d, %Y')} — {saturday.strftime('%b %d, %Y')}"

    return {
        'days': days,
        'year': year,
        'week': week,
        'today': today,
        'prev_year': prev_y,
        'prev_week': prev_w,
        'next_year': next_y,
        'next_week': next_w,
        'today_year': today_iso[0],
        'today_week': today_iso[1],
        'week_display': week_display,
        'is_readonly': is_readonly,
        'child_id': child_id,
        'child_name': child_name,
        'child': child,
    }


@login_required
@role_required('student')
def calendar_view(request, year=None, week=None):
    """Weekly calendar for a student showing Mon–Sat lessons.

    URL params ``year`` and ``week`` are ISO year/week integers.
    Defaults to the current ISO week when omitted.
    """
    today = datetime.date.today()
    iso_year, iso_week, _ = today.isocalendar()
    if year is None or week is None:
        year, week = iso_year, iso_week

    child = getattr(request.user, 'child_profile', None)
    ctx = _build_calendar_context(child, year, week, today, is_readonly=False)
    return render(request, 'tracker/calendar.html', ctx)


@login_required
@role_required('student')
def lesson_detail_view(request, scheduled_id):
    """Return JSON details for a single scheduled lesson.

    Ownership check: the lesson must belong to the student's child profile.
    """
    child = getattr(request.user, 'child_profile', None)
    sl = get_object_or_404(ScheduledLesson, pk=scheduled_id)

    if child is None or sl.child_id != child.pk:
        return JsonResponse({'error': 'forbidden'}, status=403)

    log = getattr(sl, 'log', None)
    evidence_count = log.evidence_files.count() if log else 0
    evidence_files = [
        {
            'id': ef.pk,
            'filename': ef.original_filename,
            'uploaded_at': ef.uploaded_at.strftime('%d %b %Y'),
        }
        for ef in log.evidence_files.all()
    ] if log else []

    return JsonResponse({
        'id': sl.pk,
        'lesson_title': sl.lesson.lesson_title,
        'unit_title': sl.lesson.unit_title,
        'subject_name': sl.enrolled_subject.subject_name,
        'scheduled_date': sl.scheduled_date.strftime('%d %b %Y'),
        'lesson_url': sl.lesson.lesson_url,
        'colour_hex': sl.enrolled_subject.colour_hex,
        'status': log.status if log else 'pending',
        'mastery': log.mastery if log else 'unset',
        'student_notes': log.student_notes if log else '',
        'evidence_count': evidence_count,
        'evidence_files': evidence_files,
    })


@login_required
@role_required('student')
@require_POST
def update_lesson_status_view(request, scheduled_id):
    """Accept a POST {status: 'complete'|'skipped'} and persist it to LessonLog.

    Ownership is verified: the lesson must belong to the authenticated
    student's child profile.  Returns JSON on both success and error.
    """
    child = getattr(request.user, 'child_profile', None)
    sl = get_object_or_404(ScheduledLesson, pk=scheduled_id)

    if child is None or sl.child_id != child.pk:
        return JsonResponse({'error': 'forbidden'}, status=403)

    new_status = request.POST.get('status', '')
    if new_status not in ('complete', 'skipped'):
        return JsonResponse({'error': 'invalid status'}, status=400)

    log, _ = LessonLog.objects.get_or_create(scheduled_lesson=sl)
    log.status = new_status
    if new_status == 'complete':
        log.completed_at = timezone.now()
    log.save()

    return JsonResponse({
        'success': True,
        'status': log.status,
        'message': 'Lesson marked as complete.' if new_status == 'complete' else 'Lesson skipped.',
    })


@login_required
@role_required('student')
@require_POST
def update_mastery_view(request, scheduled_id):
    """Accept a POST {mastery: 'green'|'amber'|'red'} and persist it to LessonLog.

    Ownership is verified: the lesson must belong to the authenticated
    student's child profile.  Returns JSON on both success and error.
    """
    child = getattr(request.user, 'child_profile', None)
    sl = get_object_or_404(ScheduledLesson, pk=scheduled_id)

    if child is None or sl.child_id != child.pk:
        return JsonResponse({'error': 'forbidden'}, status=403)

    new_mastery = request.POST.get('mastery', '')
    if new_mastery not in ('green', 'amber', 'red'):
        return JsonResponse({'error': 'invalid mastery'}, status=400)

    log, _ = LessonLog.objects.get_or_create(scheduled_lesson=sl)
    log.mastery = new_mastery
    log.save()

    return JsonResponse({
        'success': True,
        'mastery': log.mastery,
    })


@login_required
@role_required('student')
@require_POST
def save_notes_view(request, scheduled_id):
    """Accept a POST {notes: string} and persist it to LessonLog.student_notes.

    Ownership is verified: the lesson must belong to the authenticated
    student's child profile.  Notes are capped at 1000 characters.
    Returns JSON on both success and error.
    """
    child = getattr(request.user, 'child_profile', None)
    sl = get_object_or_404(ScheduledLesson, pk=scheduled_id)

    if child is None or sl.child_id != child.pk:
        return JsonResponse({'error': 'forbidden'}, status=403)

    notes = request.POST.get('notes', '')
    if len(notes) > 1000:
        return JsonResponse({'error': 'notes too long'}, status=400)

    log, _ = LessonLog.objects.get_or_create(scheduled_lesson=sl)
    log.student_notes = notes
    log.save()

    return JsonResponse({'success': True, 'student_notes': log.student_notes})


@login_required
@role_required('student')
@require_POST
def reschedule_lesson_view(request, scheduled_id):
    """Accept a POST {new_date: 'YYYY-MM-DD'} and move the lesson to that date.

    Ownership is verified.  new_date must be strictly in the future (> today).
    Updates ScheduledLesson.scheduled_date and LessonLog.rescheduled_to.
    Returns JSON on both success and error.
    """
    child = getattr(request.user, 'child_profile', None)
    sl = get_object_or_404(ScheduledLesson, pk=scheduled_id)

    if child is None or sl.child_id != child.pk:
        return JsonResponse({'error': 'forbidden'}, status=403)

    raw_date = request.POST.get('new_date', '').strip()
    try:
        new_date = datetime.date.fromisoformat(raw_date)
    except ValueError:
        return JsonResponse({'error': 'invalid date'}, status=400)

    if new_date <= datetime.date.today():
        return JsonResponse({'error': 'date must be in the future'}, status=400)

    sl.scheduled_date = new_date
    sl.save()

    log, _ = LessonLog.objects.get_or_create(scheduled_lesson=sl)
    log.rescheduled_to = new_date
    log.save()

    return JsonResponse({'success': True, 'new_date': new_date.isoformat()})


_ALLOWED_EVIDENCE_TYPES = frozenset({
    'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/svg+xml',
    'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
})


@login_required
@role_required('student')
@require_POST
def upload_evidence_view(request, scheduled_id):
    """Accept a multipart POST with a 'file' field and store it on Cloudinary.

    Validates ownership and restricts uploads to images, PDF, .doc, .docx.
    Creates a LessonLog if one does not yet exist.
    Returns JSON: {success, file_id, filename, uploaded_at}.
    """
    child = getattr(request.user, 'child_profile', None)
    sl = get_object_or_404(ScheduledLesson, pk=scheduled_id)

    if child is None or sl.child_id != child.pk:
        return JsonResponse({'error': 'forbidden'}, status=403)

    uploaded_file = request.FILES.get('file')
    if not uploaded_file:
        return JsonResponse({'error': 'no file provided'}, status=400)

    content_type = (uploaded_file.content_type or '').split(';')[0].strip().lower()
    if not (content_type.startswith('image/') or content_type in _ALLOWED_EVIDENCE_TYPES):
        return JsonResponse({'error': 'invalid file type'}, status=400)

    log, _ = LessonLog.objects.get_or_create(scheduled_lesson=sl)
    try:
        evidence = EvidenceFile.objects.create(
            lesson_log=log,
            file=uploaded_file,
            original_filename=uploaded_file.name,
            uploaded_by=request.user,
        )
    except Exception as exc:
        return JsonResponse({'success': False, 'error': f'Upload failed: {exc}'}, status=500)

    return JsonResponse({
        'success': True,
        'file_id': evidence.pk,
        'filename': evidence.original_filename,
        'uploaded_at': evidence.uploaded_at.strftime('%d %b %Y'),
        'evidence_count': log.evidence_files.count(),
    })


@login_required
@role_required('student')
@require_POST
def delete_evidence_view(request, file_id):
    """Delete an evidence file from Cloudinary and the database.

    Only the student who uploaded the file may delete it.
    Returns JSON: {success, evidence_count}.
    """
    import cloudinary.uploader

    evidence = get_object_or_404(EvidenceFile, pk=file_id)
    if evidence.uploaded_by_id != request.user.pk:
        return JsonResponse({'error': 'forbidden'}, status=403)

    public_id = (
        evidence.file.public_id
        if hasattr(evidence.file, 'public_id')
        else str(evidence.file)
    )
    try:
        cloudinary.uploader.destroy(public_id, resource_type='raw')
    except Exception:
        pass  # best-effort; always delete DB record

    log = evidence.lesson_log
    evidence.delete()

    return JsonResponse({
        'success': True,
        'evidence_count': log.evidence_files.count(),
    })


@login_required
@role_required('parent')
def parent_calendar_home_view(request):
    """Redirect a parent to their first active child's calendar, or to
    the child list if they have no children yet."""
    from scheduler.models import Child as ChildModel
    from django.urls import reverse
    child = ChildModel.objects.filter(parent=request.user, is_active=True).first()
    if child:
        return redirect(reverse('tracker:parent_calendar', kwargs={'child_id': child.pk}))
    return redirect('scheduler:child_list')


@login_required
@role_required('parent')
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

    ctx = _build_calendar_context(
        child, year, week, today,
        is_readonly=True, child_id=child_id, child_name=child.first_name,
    )
    ctx['siblings'] = siblings
    return render(request, 'tracker/calendar.html', ctx)


def _build_ical(child, scheduled_lessons, vacations):
    """Build a minimal RFC 5545 iCalendar string for a child's schedule."""
    lines = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        f'PRODID:-//EduTrack//Schedule for {child.first_name}//EN',
        'CALSCALE:GREGORIAN',
        'METHOD:PUBLISH',
        f'X-WR-CALNAME:{child.first_name} — EduTrack Schedule',
    ]

    for sl in scheduled_lessons:
        uid = f'lesson-{sl.pk}@edutrack'
        dtstart = sl.scheduled_date.strftime('%Y%m%d')
        dtend = (sl.scheduled_date + datetime.timedelta(days=1)).strftime('%Y%m%d')
        summary = f'{sl.enrolled_subject.subject_name}: {sl.lesson.lesson_title}'
        lines += [
            'BEGIN:VEVENT',
            f'UID:{uid}',
            f'DTSTART;VALUE=DATE:{dtstart}',
            f'DTEND;VALUE=DATE:{dtend}',
            f'SUMMARY:{summary}',
            'END:VEVENT',
        ]

    for vac in vacations:
        uid = f'vac-{vac.pk}@edutrack'
        dtstart = vac.start_date.strftime('%Y%m%d')
        dtend = (vac.end_date + datetime.timedelta(days=1)).strftime('%Y%m%d')
        lines += [
            'BEGIN:VEVENT',
            f'UID:{uid}',
            f'DTSTART;VALUE=DATE:{dtstart}',
            f'DTEND;VALUE=DATE:{dtend}',
            f'SUMMARY:{vac.name}',
            'TRANSP:TRANSPARENT',
            'END:VEVENT',
        ]

    lines.append('END:VCALENDAR')
    return '\r\n'.join(lines) + '\r\n'


@login_required
@role_required('student')
def export_ical_view(request):
    """Download the student's full schedule as an iCalendar (.ics) file."""
    child = getattr(request.user, 'child_profile', None)
    if child is None:
        from django.http import HttpResponseNotFound
        return HttpResponseNotFound('No child profile found.')

    lessons = (
        ScheduledLesson.objects
        .filter(child=child)
        .select_related('lesson', 'enrolled_subject')
        .order_by('scheduled_date')
    )
    vacations = Vacation.objects.filter(child=child)

    content = _build_ical(child, lessons, vacations)
    response = HttpResponse(content, content_type='text/calendar; charset=utf-8')
    response['Content-Disposition'] = (
        f'attachment; filename="{child.first_name}_schedule.ics"'
    )
    return response


@login_required
@role_required('parent')
def parent_export_ical_view(request, child_id):
    """Download a child's full schedule as an iCalendar (.ics) file (parent)."""
    from scheduler.models import Child as ChildModel
    child = get_object_or_404(ChildModel, pk=child_id)

    if child.parent_id != request.user.pk:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    lessons = (
        ScheduledLesson.objects
        .filter(child=child)
        .select_related('lesson', 'enrolled_subject')
        .order_by('scheduled_date')
    )
    vacations = Vacation.objects.filter(child=child)

    content = _build_ical(child, lessons, vacations)
    response = HttpResponse(content, content_type='text/calendar; charset=utf-8')
    response['Content-Disposition'] = (
        f'attachment; filename="{child.first_name}_schedule.ics"'
    )
    return response
