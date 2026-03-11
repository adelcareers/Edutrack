"""Views for the scheduler app."""

import csv
import datetime
import io
import json
import uuid

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.models import User
from django.http import HttpResponseForbidden

from django.db.models import Count

from accounts.decorators import role_required
from accounts.forms import StudentCreationForm
from accounts.models import UserProfile
from curriculum.models import Lesson
from scheduler.forms import NewStudentModalForm
from scheduler.models import Child, EnrolledSubject, ScheduledLesson
from scheduler.services import generate_schedule

SUBJECT_COLOUR_PALETTE = [
    '#E63946', '#2A9D8F', '#E9C46A', '#F4A261', '#264653',
    '#8338EC', '#3A86FF', '#FB5607', '#FFBE0B', '#06D6A0',
]


@role_required('parent')
def child_list_view(request):
    """Display all active children for the parent."""
    today = datetime.date.today()
    week_start = today - datetime.timedelta(days=today.weekday())
    week_end = week_start + datetime.timedelta(days=6)

    children = Child.objects.filter(parent=request.user, is_active=True)

    # Build per-child progress summaries
    summaries = []
    for child in children:
        total_scheduled = child.scheduled_lessons.count()
        total_complete = child.scheduled_lessons.filter(log__status='complete').count()
        completed_this_week = (
            child.scheduled_lessons
            .filter(
                scheduled_date__gte=week_start,
                scheduled_date__lte=week_end,
                log__status='complete',
            )
            .count()
        )
        pct_complete = (
            round(total_complete / total_scheduled * 100) if total_scheduled else 0
        )
        summaries.append({
            'child': child,
            'total_scheduled': total_scheduled,
            'total_complete': total_complete,
            'completed_this_week': completed_this_week,
            'pct_complete': pct_complete,
        })

    return render(request, 'scheduler/child_list.html', {
        'summaries': summaries,
    })


@role_required('parent')
def delete_child_view(request, child_id):
    """Delete a child after the parent confirms by typing the child's name."""
    child = get_object_or_404(Child, pk=child_id, parent=request.user)

    if request.method == 'POST':
        confirm_name = request.POST.get('confirm_name', '').strip()
        if confirm_name == child.first_name:
            child_name = child.first_name
            child.delete()
            messages.success(request, f"{child_name} has been deleted.")
        else:
            messages.error(request, "Name did not match. Student not deleted.")

    return redirect('scheduler:child_list')


def _build_subject_groups(child, user):
    """Return grouped subject data with preview colours for ``subject_selection_view``.

    Includes curriculum subjects for the child's school year plus any custom
    subjects created by the parent.  A palette colour is pre-assigned to every
    subject so the grid can show swatches before the form is submitted.

    Returns a dict:  {key_stage: [{subject_name, total_lessons, preview_colour, is_custom, source_year}]}
    """
    # Standard curriculum subjects for this year
    lessons_qs = (
        Lesson.objects
        .filter(year=child.school_year, is_custom=False)
        .values('key_stage', 'subject_name')
        .annotate(total_lessons=Count('id'))
        .order_by('key_stage', 'subject_name')
    )

    # Custom subjects created by this parent for this year
    custom_qs = (
        Lesson.objects
        .filter(is_custom=True, created_by=user, year=child.school_year)
        .values('subject_name')
        .annotate(total_lessons=Count('id'))
        .order_by('subject_name')
    )

    grouped = {}
    colour_index = 0

    for row in lessons_qs:
        grouped.setdefault(row['key_stage'], []).append({
            'subject_name': row['subject_name'],
            'total_lessons': row['total_lessons'],
            'preview_colour': SUBJECT_COLOUR_PALETTE[colour_index % len(SUBJECT_COLOUR_PALETTE)],
            'is_custom': False,
            'source_year': '',
        })
        colour_index += 1

    for row in custom_qs:
        grouped.setdefault('Custom', []).append({
            'subject_name': row['subject_name'],
            'total_lessons': row['total_lessons'],
            'preview_colour': SUBJECT_COLOUR_PALETTE[colour_index % len(SUBJECT_COLOUR_PALETTE)],
            'is_custom': True,
            'source_year': '',
        })
        colour_index += 1

    return grouped


@role_required('parent')
def subject_selection_view(request, child_id):
    """Let a parent choose subjects and assign days of the week for each.

    GET: renders the scheduling grid — a table of all available subjects
    (curriculum + custom) with Mon–Fri day-checkboxes per row and a
    pre-assigned colour swatch.

    POST: for each selected subject reads the ``days_<name>`` checkbox list,
    derives ``lessons_per_week`` from the number of chosen days, creates an
    ``EnrolledSubject`` and redirects to the schedule generation page.
    """
    child = get_object_or_404(Child, pk=child_id)

    if child.parent != request.user:
        return HttpResponseForbidden("You do not have permission to manage this child.")

    grouped = _build_subject_groups(child, request.user)

    if request.method == 'POST':
        selected_subjects = request.POST.getlist('subjects')
        if not selected_subjects:
            messages.error(request, "Please select at least one subject.")
            return render(request, 'scheduler/subject_selection.html', {
                'child': child,
                'grouped': grouped,
                'day_choices': [(0, 'Mon'), (1, 'Tue'), (2, 'Wed'), (3, 'Thu'), (4, 'Fri')],
            })

        # Delete any existing enrolments before recreating (idempotent re-submission)
        child.enrolled_subjects.all().delete()

        # Flatten all subjects in order to replicate the colour index
        all_subjects_ordered = [
            s['subject_name']
            for subjects in grouped.values()
            for s in subjects
        ]

        to_create = []
        for subject_name in selected_subjects:
            raw_days = request.POST.getlist(f'days_{subject_name}')
            # Keep only valid weekday ints 0-4
            days = sorted({int(d) for d in raw_days if d.isdigit() and 0 <= int(d) <= 4})
            if not days:
                days = [0, 1, 2, 3, 4]  # default to all weekdays if none ticked
            days_str = ','.join(str(d) for d in days)
            pace = len(days)

            key_stage = (
                Lesson.objects
                .filter(year=child.school_year, subject_name=subject_name)
                .values_list('key_stage', flat=True)
                .first() or 'Custom'
            )
            palette_index = (
                all_subjects_ordered.index(subject_name)
                if subject_name in all_subjects_ordered
                else len(to_create)
            )
            to_create.append(EnrolledSubject(
                child=child,
                subject_name=subject_name,
                key_stage=key_stage,
                lessons_per_week=pace,
                days_of_week=days_str,
                colour_hex=SUBJECT_COLOUR_PALETTE[palette_index % len(SUBJECT_COLOUR_PALETTE)],
            ))

        EnrolledSubject.objects.bulk_create(to_create)
        messages.success(
            request,
            f"{len(to_create)} subject(s) enrolled for {child.first_name}. "
            "Ready to generate your schedule!",
        )
        return redirect(f'/children/{child.pk}/generate/')

    return render(request, 'scheduler/subject_selection.html', {
        'child': child,
        'grouped': grouped,
        'day_choices': [(0, 'Mon'), (1, 'Tue'), (2, 'Wed'), (3, 'Thu'), (4, 'Fri')],
    })


@role_required('parent')
def generate_schedule_view(request, child_id):
    """Show a summary of subjects to be scheduled and, on POST, generate the schedule.

    GET: renders a confirmation page listing each enrolled subject with its
    curriculum lesson count.

    POST: deletes any existing ScheduledLesson rows for this child (idempotent
    regeneration), calls ``generate_schedule()``, flashes a success message
    containing the total count, then redirects to the child list.
    """
    child = get_object_or_404(Child, pk=child_id)

    if child.parent != request.user:
        return HttpResponseForbidden("You do not have permission to manage this child.")

    enrolled_subjects = list(child.enrolled_subjects.filter(is_active=True))

    if request.method == 'POST':
        child.scheduled_lessons.all().delete()
        count = generate_schedule(child, enrolled_subjects)
        messages.success(
            request,
            f"{child.first_name}'s schedule is ready — {count} lessons scheduled across 180 days.",
        )
        return redirect('scheduler:child_list')

    subject_summaries = []
    for subject in enrolled_subjects:
        total_lessons = (
            Lesson.objects
            .filter(subject_name=subject.subject_name, year=child.school_year)
            .count()
        )
        subject_summaries.append({
            'subject': subject,
            'total_lessons': total_lessons,
        })

    return render(request, 'scheduler/generate_schedule.html', {
        'child': child,
        'subject_summaries': subject_summaries,
    })


@role_required('parent')
def create_student_login_view(request, child_id):
    """Allow a parent to create login credentials for one of their children.

    The view enforces ownership — a parent can only create credentials for
    their own children.  Once the form is submitted successfully a new
    ``User`` (role='student') is created and linked to ``Child.student_user``.
    """
    child = get_object_or_404(Child, pk=child_id)

    if child.parent != request.user:
        return HttpResponseForbidden("You do not have permission to manage this child.")

    if child.student_user is not None:
        messages.info(
            request,
            f"{child.first_name} already has login credentials "
            f"(username: {child.student_user.username}).",
        )
        return redirect('home')

    if request.method == 'POST':
        form = StudentCreationForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password1']
            student_user = User.objects.create_user(username=username, password=password)
            UserProfile.objects.create(user=student_user, role='student')
            child.student_user = student_user
            child.save()
            messages.success(
                request,
                f"Login created for {child.first_name}. "
                f"They can now sign in as \"{username}\".",
            )
            return redirect('home')
    else:
        form = StudentCreationForm()

    return render(request, 'scheduler/create_student_login.html', {
        'form': form,
        'child': child,
    })


@role_required('parent')
def child_new_view(request):
    """Inline new-student form — same layout as child_detail but for creation."""
    raw_years = Lesson.objects.values_list('year', flat=True).distinct()
    school_years = sorted(
        set(raw_years),
        key=lambda y: int(y.split()[-1]) if y.split()[-1].isdigit() else 99,
    )

    errors = {}
    form_data = {}

    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        school_year = request.POST.get('school_year', '').strip()
        form_data = {'first_name': first_name, 'school_year': school_year}

        if not first_name:
            errors['first_name'] = 'Student name is required.'
        if not school_year:
            errors['school_year'] = 'School year is required.'

        if not errors:
            today = datetime.date.today()
            academic_start = (
                datetime.date(today.year, 9, 1)
                if today.month >= 9
                else datetime.date(today.year - 1, 9, 1)
            )
            child = Child(
                parent=request.user,
                first_name=first_name,
                school_year=school_year,
                birth_month=today.month,
                birth_year=today.year - 10,
                academic_year_start=academic_start,
            )
            if request.FILES.get('photo'):
                child.photo = request.FILES['photo']
            child.save()
            messages.success(request, f"{child.first_name} added! Now set up their account and courses.")
            return redirect('scheduler:child_detail', child_id=child.pk)

    return render(request, 'scheduler/child_new.html', {
        'school_years': school_years,
        'errors': errors,
        'form_data': form_data,
    })


@role_required('parent')
def child_detail_view(request, child_id):
    """Student detail page: edit info, create login, view enrolled courses."""
    child = get_object_or_404(Child, pk=child_id, parent=request.user)

    raw_years = Lesson.objects.values_list('year', flat=True).distinct()
    school_years = sorted(
        set(raw_years),
        key=lambda y: int(y.split()[-1]) if y.split()[-1].isdigit() else 99,
    )

    info_errors = {}
    login_form = StudentCreationForm()

    if request.method == 'POST':
        if 'save_student' in request.POST:
            first_name = request.POST.get('first_name', '').strip()
            school_year = request.POST.get('school_year', '').strip()
            if not first_name:
                info_errors['first_name'] = 'Student name is required.'
            if not school_year:
                info_errors['school_year'] = 'School year is required.'
            if not info_errors:
                child.first_name = first_name
                child.school_year = school_year
                if request.FILES.get('photo'):
                    child.photo = request.FILES['photo']
                child.save()
                messages.success(request, f"{child.first_name} updated successfully.")
                return redirect('scheduler:child_detail', child_id=child.pk)

        elif 'create_login' in request.POST:
            if child.student_user is not None:
                messages.info(request, f"{child.first_name} already has login credentials.")
                return redirect('scheduler:child_detail', child_id=child.pk)
            login_form = StudentCreationForm(request.POST)
            if login_form.is_valid():
                username = login_form.cleaned_data['username']
                password = login_form.cleaned_data['password1']
                student_user = User.objects.create_user(username=username, password=password)
                UserProfile.objects.create(user=student_user, role='student')
                child.student_user = student_user
                child.save()
                messages.success(request, f"Login created for {child.first_name}.")
                return redirect('scheduler:child_detail', child_id=child.pk)

    enrolled_subjects = child.enrolled_subjects.filter(is_active=True)
    total_days_attended = child.scheduled_lessons.filter(log__status='complete').count()

    return render(request, 'scheduler/child_detail.html', {
        'child': child,
        'school_years': school_years,
        'login_form': login_form,
        'info_errors': info_errors,
        'enrolled_subjects': enrolled_subjects,
        'total_days_attended': total_days_attended,
    })


@role_required('parent')
def custom_subject_view(request, child_id):
    """Three-path custom subject creator: import from another year, manual entry, or CSV.

    All three POST paths bulk-create ``Lesson`` rows with ``is_custom=True`` and
    ``created_by=request.user``, then redirect to the subject selection page so the
    parent can enrol the newly created subject immediately.
    """
    child = get_object_or_404(Child, pk=child_id, parent=request.user)

    # Distinct year groups from the curriculum (for the import-from-year tab)
    raw_years = Lesson.objects.filter(is_custom=False).values_list('year', flat=True).distinct()
    all_years = sorted(
        set(raw_years),
        key=lambda y: int(y.split()[-1]) if y.split()[-1].isdigit() else 99,
    )

    # Subjects available per year (for JS to populate the subject select in the import tab)
    year_subjects = {}
    for yr in all_years:
        year_subjects[yr] = sorted(
            Lesson.objects
            .filter(year=yr, is_custom=False)
            .values_list('subject_name', flat=True)
            .distinct()
        )

    if request.method == 'POST':
        tab = request.POST.get('tab', '')

        # ── TAB 1: Import from another year ───────────────────────────────────
        if tab == 'import_year':
            source_year = request.POST.get('source_year', '').strip()
            subject_name = request.POST.get('import_subject_name', '').strip()
            if not source_year or not subject_name:
                messages.error(request, 'Please select a year group and subject to import.')
            else:
                lesson_count = Lesson.objects.filter(
                    year=source_year, subject_name=subject_name, is_custom=False
                ).count()
                if lesson_count == 0:
                    messages.error(request, f'No lessons found for "{subject_name}" in {source_year}.')
                else:
                    # Ensure there isn't already a custom record; create a
                    # single placeholder lesson that points to this source year.
                    display_name = f'{subject_name} (from {source_year})'
                    placeholder_url = f'custom://import/{uuid.uuid4()}'
                    Lesson.objects.get_or_create(
                        lesson_url=placeholder_url,
                        defaults=dict(
                            key_stage='Custom',
                            subject_name=display_name,
                            programme_slug='custom',
                            year=child.school_year,
                            unit_slug='import',
                            unit_title='Imported',
                            lesson_number=1,
                            lesson_title=f'Import placeholder for {display_name}',
                            is_custom=True,
                            created_by=request.user,
                        ),
                    )
                    # Tag the enrolled subject with source_year so the
                    # scheduler pulls lessons from the right year.
                    EnrolledSubject.objects.update_or_create(
                        child=child, subject_name=display_name,
                        defaults=dict(
                            key_stage='Custom',
                            lessons_per_week=1,
                            days_of_week='0,1,2,3,4',
                            source_year=source_year,
                            colour_hex=SUBJECT_COLOUR_PALETTE[
                                child.enrolled_subjects.count() % len(SUBJECT_COLOUR_PALETTE)
                            ],
                            is_active=True,
                        ),
                    )
                    messages.success(
                        request,
                        f'"{display_name}" imported — now choose its days and confirm.'
                    )
                    return redirect('scheduler:subject_selection', child_id=child.pk)

        # ── TAB 2: Manual entry ───────────────────────────────────────────────
        elif tab == 'manual':
            subject_name = request.POST.get('manual_subject_name', '').strip()
            raw_titles = request.POST.get('lesson_titles', '').strip()
            titles = [t.strip() for t in raw_titles.splitlines() if t.strip()]
            if not subject_name:
                messages.error(request, 'Please enter a subject name.')
            elif not titles:
                messages.error(request, 'Please enter at least one lesson title.')
            else:
                to_create = []
                for i, title in enumerate(titles, start=1):
                    to_create.append(Lesson(
                        key_stage='Custom',
                        subject_name=subject_name,
                        programme_slug='custom',
                        year=child.school_year,
                        unit_slug='manual',
                        unit_title=subject_name,
                        lesson_number=i,
                        lesson_title=title,
                        lesson_url=f'custom://manual/{uuid.uuid4()}',
                        is_custom=True,
                        created_by=request.user,
                    ))
                Lesson.objects.bulk_create(to_create)
                messages.success(
                    request,
                    f'{len(to_create)} lessons created for "{subject_name}". '
                    'Now choose its days and confirm.'
                )
                return redirect('scheduler:subject_selection', child_id=child.pk)

        # ── TAB 3: CSV upload ─────────────────────────────────────────────────
        elif tab == 'csv':
            subject_name = request.POST.get('csv_subject_name', '').strip()
            csv_file = request.FILES.get('csv_file')
            if not subject_name:
                messages.error(request, 'Please enter a subject name.')
            elif not csv_file:
                messages.error(request, 'Please upload a CSV file.')
            else:
                try:
                    decoded = csv_file.read().decode('utf-8-sig')
                    reader = csv.DictReader(io.StringIO(decoded))
                    to_create = []
                    for i, row in enumerate(reader, start=1):
                        title = (row.get('lesson_title') or '').strip()
                        unit = (row.get('unit_title') or subject_name).strip()
                        custom_url = (row.get('lesson_url') or '').strip() or f'custom://csv/{uuid.uuid4()}'
                        if not title:
                            continue  # skip blank rows silently
                        to_create.append(Lesson(
                            key_stage='Custom',
                            subject_name=subject_name,
                            programme_slug='custom',
                            year=child.school_year,
                            unit_slug='csv',
                            unit_title=unit,
                            lesson_number=i,
                            lesson_title=title,
                            lesson_url=custom_url,
                            is_custom=True,
                            created_by=request.user,
                        ))
                    if not to_create:
                        messages.error(request, 'No valid rows found in the CSV. Check the lesson_title column.')
                    else:
                        Lesson.objects.bulk_create(to_create, ignore_conflicts=True)
                        messages.success(
                            request,
                            f'{len(to_create)} lessons created from CSV for "{subject_name}". '
                            'Now choose its days and confirm.'
                        )
                        return redirect('scheduler:subject_selection', child_id=child.pk)
                except Exception:
                    messages.error(request, 'Could not parse the CSV. Make sure it has a lesson_title column.')

    return render(request, 'scheduler/custom_subject.html', {
        'child': child,
        'all_years': all_years,
        'year_subjects_json': json.dumps(year_subjects),
        'child_year': child.school_year,
    })
