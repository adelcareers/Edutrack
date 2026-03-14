"""Views for the scheduler app."""

import csv
import datetime
import io
import json
import uuid

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.http import HttpResponseForbidden
from django.core.exceptions import ValidationError

from django.db.models import Count

from accounts.decorators import role_required
from accounts.forms import StudentCreationForm
from accounts.models import UserProfile
from curriculum.models import Lesson
from scheduler.forms import NewStudentModalForm
from scheduler.models import Child, CustomSubjectGroup, EnrolledSubject, ScheduledLesson
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

    Returns a dict:  {key_stage: [{subject_name, total_lessons, total_units, preview_colour, is_custom}]}
    """
    # Standard curriculum subjects for this year
    lessons_qs = (
        Lesson.objects
        .filter(year=child.school_year, is_custom=False)
        .values('key_stage', 'subject_name')
        .annotate(total_lessons=Count('id'), total_units=Count('unit_slug', distinct=True))
        .order_by('key_stage', 'subject_name')
    )

    # Custom subjects created by this parent for this year
    custom_qs = (
        Lesson.objects
        .filter(is_custom=True, created_by=user, year=child.school_year)
        .values('subject_name')
        .annotate(total_lessons=Count('id'), total_units=Count('unit_slug', distinct=True))
        .order_by('subject_name')
    )

    grouped = {}
    colour_index = 0

    for row in lessons_qs:
        grouped.setdefault(row['key_stage'], []).append({
            'subject_name': row['subject_name'],
            'total_lessons': row['total_lessons'],
            'total_units': row['total_units'],
            'preview_colour': SUBJECT_COLOUR_PALETTE[colour_index % len(SUBJECT_COLOUR_PALETTE)],
            'is_custom': False,
        })
        colour_index += 1

    for row in custom_qs:
        grouped.setdefault('Custom', []).append({
            'subject_name': row['subject_name'],
            'total_lessons': row['total_lessons'],
            'total_units': row['total_units'],
            'preview_colour': SUBJECT_COLOUR_PALETTE[colour_index % len(SUBJECT_COLOUR_PALETTE)],
            'is_custom': True,
        })
        colour_index += 1

    return grouped


@role_required('parent')
def subject_selection_view(request, child_id):
    """Step 1 of 2: parent picks subjects; lessons-per-week is set on the next page.

    GET: flat table of all subjects sorted by lesson count (desc).
    Sortable client-side by name, units, or lessons.

    POST: creates ``EnrolledSubject`` rows with default lessons_per_week=3
    (overridden on the day-assignment page), then redirects there.
    """
    child = get_object_or_404(Child, pk=child_id)

    if child.parent != request.user:
        return HttpResponseForbidden("You do not have permission to manage this child.")

    grouped = _build_subject_groups(child, request.user)

    if request.method == 'POST':
        selected_subjects = request.POST.getlist('subjects')
        if not selected_subjects:
            messages.error(request, "Please select at least one subject.")
            subjects = sorted(
                [s for ks_subjects in grouped.values() for s in ks_subjects],
                key=lambda s: s['total_lessons'],
                reverse=True,
            )
            return render(request, 'scheduler/subject_selection.html', {
                'child': child,
                'subjects': subjects,
            })

        # Delete any existing enrolments before recreating
        child.enrolled_subjects.all().delete()

        # Flatten all subjects in palette order (key_stage alpha, subject alpha)
        all_subjects_ordered = [
            s['subject_name']
            for ks_subjects in grouped.values()
            for s in ks_subjects
        ]

        to_create = []
        for subject_name in selected_subjects:
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
                lessons_per_week=3,  # default; overridden in step 2
                days_of_week='0,1,2,3,4',  # default; overridden in step 2
                colour_hex=SUBJECT_COLOUR_PALETTE[palette_index % len(SUBJECT_COLOUR_PALETTE)],
            ))

        EnrolledSubject.objects.bulk_create(to_create)
        return redirect('scheduler:schedule_days', child_id=child.pk)

    subjects = sorted(
        [s for ks_subjects in grouped.values() for s in ks_subjects],
        key=lambda s: s['total_lessons'],
        reverse=True,
    )
    return render(request, 'scheduler/subject_selection.html', {
        'child': child,
        'subjects': subjects,
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
def schedule_days_view(request, child_id):
    """Step 2 of 2: set lessons-per-week and assign days for each enrolled subject.

    GET: table showing each enrolled subject with curriculum stats,
    a lessons-per-week number input, and Mon–Fri day checkboxes.

    POST: reads ``lpw_<pk>`` (lessons per week) and ``days_<pk>`` checkboxes,
    updates both fields on each ``EnrolledSubject``, then redirects to the
    generate-schedule confirmation.
    """
    child = get_object_or_404(Child, pk=child_id)

    if child.parent != request.user:
        return HttpResponseForbidden("You do not have permission to manage this child.")

    enrolled_subjects = list(child.enrolled_subjects.filter(is_active=True))

    if not enrolled_subjects:
        messages.error(request, "Please select at least one subject first.")
        return redirect('scheduler:subject_selection', child_id=child.pk)

    if request.method == 'POST':
        day_choices_vals = [0, 1, 2, 3, 4]
        for subject in enrolled_subjects:
            raw_days = request.POST.getlist(f'days_{subject.pk}')
            days = sorted({int(d) for d in raw_days if d.isdigit() and int(d) in day_choices_vals})
            if not days:
                days = day_choices_vals
            subject.days_of_week = ','.join(str(d) for d in days)

            raw_lpw = request.POST.get(f'lpw_{subject.pk}', '')
            if raw_lpw:
                try:
                    subject.lessons_per_week = max(1, min(10, int(raw_lpw)))
                except (ValueError, TypeError):
                    pass

            subject.save(update_fields=['days_of_week', 'lessons_per_week'])

        return redirect('scheduler:generate_schedule', child_id=child.pk)

    day_choices = [(0, 'Mon'), (1, 'Tue'), (2, 'Wed'), (3, 'Thu'), (4, 'Fri')]

    # Fetch curriculum stats for each enrolled subject
    subject_names = [s.subject_name for s in enrolled_subjects]
    stats_qs = (
        Lesson.objects
        .filter(year=child.school_year, subject_name__in=subject_names)
        .values('subject_name')
        .annotate(total_lessons=Count('id'), total_units=Count('unit_slug', distinct=True))
    )
    stats_by_name = {row['subject_name']: row for row in stats_qs}

    subject_rows = []
    for subject in enrolled_subjects:
        checked = {int(d) for d in subject.days_of_week.split(',') if d.isdigit()}
        if not checked:
            checked = {0, 1, 2, 3, 4}
        stats = stats_by_name.get(subject.subject_name, {'total_lessons': 0, 'total_units': 0})
        subject_rows.append({
            'subject': subject,
            'checked_days': checked,
            'total_lessons': stats['total_lessons'],
            'total_units': stats['total_units'],
        })

    return render(request, 'scheduler/schedule_days.html', {
        'child': child,
        'subject_rows': subject_rows,
        'day_choices': day_choices,
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
    login_manage_errors = {}
    login_manage_data = {}
    login_section_open = child.student_user is None

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
            login_section_open = True
            if login_form.is_valid():
                username = login_form.cleaned_data['username']
                password = login_form.cleaned_data['password1']
                student_user = User.objects.create_user(username=username, password=password)
                UserProfile.objects.create(user=student_user, role='student')
                child.student_user = student_user
                child.save()
                messages.success(request, f"Login created for {child.first_name}.")
                return redirect('scheduler:child_detail', child_id=child.pk)

        elif 'update_login_username' in request.POST:
            login_section_open = True
            if child.student_user is None:
                messages.error(request, 'Create a student login first.')
                return redirect('scheduler:child_detail', child_id=child.pk)

            new_username = request.POST.get('new_username', '').strip()
            login_manage_data['new_username'] = new_username

            if not new_username:
                login_manage_errors['new_username'] = 'Username is required.'
            elif (
                User.objects
                .filter(username__iexact=new_username)
                .exclude(pk=child.student_user.pk)
                .exists()
            ):
                login_manage_errors['new_username'] = 'This username is already taken.'
            else:
                child.student_user.username = new_username
                child.student_user.save(update_fields=['username'])
                messages.success(
                    request,
                    f"{child.first_name}'s login username was updated.",
                )
                return redirect('scheduler:child_detail', child_id=child.pk)

        elif 'reset_login_password' in request.POST:
            login_section_open = True
            if child.student_user is None:
                messages.error(request, 'Create a student login first.')
                return redirect('scheduler:child_detail', child_id=child.pk)

            new_password1 = request.POST.get('new_password1', '')
            new_password2 = request.POST.get('new_password2', '')

            if not new_password1:
                login_manage_errors['new_password1'] = 'Password is required.'
            elif new_password1 != new_password2:
                login_manage_errors['new_password2'] = 'Passwords do not match.'
            else:
                try:
                    validate_password(new_password1, user=child.student_user)
                except ValidationError as exc:
                    login_manage_errors['new_password1'] = ' '.join(exc.messages)
                else:
                    child.student_user.set_password(new_password1)
                    child.student_user.save(update_fields=['password'])
                    messages.success(
                        request,
                        f"{child.first_name}'s password was reset.",
                    )
                    return redirect('scheduler:child_detail', child_id=child.pk)

    enrolled_subjects = child.enrolled_subjects.filter(is_active=True)
    total_days_attended = child.scheduled_lessons.filter(log__status='complete').count()

    return render(request, 'scheduler/child_detail.html', {
        'child': child,
        'school_years': school_years,
        'login_form': login_form,
        'login_manage_errors': login_manage_errors,
        'login_manage_data': login_manage_data,
        'login_section_open': login_section_open,
        'info_errors': info_errors,
        'enrolled_subjects': enrolled_subjects,
        'total_days_attended': total_days_attended,
    })


@role_required('parent')
def custom_subject_view(request, child_id):
    """Three-path custom subject creator: import from another year, manual entry, or CSV.

    Import path creates EnrolledSubject rows with source_year so the
    scheduler pulls lessons from the original year.

    Manual and CSV paths bulk-create ``Lesson`` rows with ``is_custom=True``
    and link them to a ``CustomSubjectGroup`` for easy management later.
    All lessons are also immediately enrolled for ``child``.
    """
    child = get_object_or_404(Child, pk=child_id, parent=request.user)

    raw_years = Lesson.objects.filter(is_custom=False).values_list('year', flat=True).distinct()
    all_years = sorted(
        set(raw_years),
        key=lambda y: int(y.split()[-1]) if y.split()[-1].isdigit() else 99,
    )

    year_subjects = {}
    for yr in all_years:
        year_subjects[yr] = sorted(
            Lesson.objects
            .filter(year=yr, is_custom=False)
            .values_list('subject_name', flat=True)
            .distinct()
        )

    # Distinct key stages for dropdowns
    key_stages = sorted(
        Lesson.objects.filter(is_custom=False)
        .values_list('key_stage', flat=True)
        .distinct()
    )

    if request.method == 'POST':
        tab = request.POST.get('tab', '')

        # ── TAB 1: Import one or more subjects from another year ──────────────
        if tab == 'import_year':
            source_year = request.POST.get('source_year', '').strip()
            subject_names = request.POST.getlist('import_subjects')
            if not source_year or not subject_names:
                messages.error(request, 'Please select a year group and at least one subject.')
            else:
                imported = 0
                for subject_name in subject_names:
                    lesson_count = Lesson.objects.filter(
                        year=source_year, subject_name=subject_name, is_custom=False
                    ).count()
                    if lesson_count == 0:
                        continue
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
                    EnrolledSubject.objects.update_or_create(
                        child=child, subject_name=display_name,
                        defaults=dict(
                            key_stage='Custom',
                            lessons_per_week=3,
                            days_of_week='0,1,2,3,4',
                            source_year=source_year,
                            colour_hex=SUBJECT_COLOUR_PALETTE[
                                child.enrolled_subjects.count() % len(SUBJECT_COLOUR_PALETTE)
                            ],
                            is_active=True,
                        ),
                    )
                    imported += 1

                if imported:
                    messages.success(
                        request,
                        f'{imported} subject(s) imported from {source_year} — '
                        'now set lessons/week and choose days.'
                    )
                    return redirect('scheduler:subject_selection', child_id=child.pk)
                else:
                    messages.error(request, 'No lessons found for the selected subjects.')

        # ── TAB 2: Manual entry ───────────────────────────────────────────────
        elif tab == 'manual':
            subject_name = request.POST.get('manual_subject_name', '').strip()
            key_stage = request.POST.get('manual_key_stage', 'Custom').strip() or 'Custom'
            unit_title = request.POST.get('manual_unit_title', '').strip() or subject_name
            lesson_titles = request.POST.getlist('lesson_title[]')
            lesson_urls   = request.POST.getlist('lesson_url[]')
            lesson_titles = [t.strip() for t in lesson_titles if t.strip()]

            if not subject_name:
                messages.error(request, 'Please enter a subject name.')
            elif not lesson_titles:
                messages.error(request, 'Please add at least one lesson.')
            else:
                group = CustomSubjectGroup.objects.create(
                    parent=request.user,
                    subject_name=subject_name,
                    year=child.school_year,
                )
                to_create = []
                for i, title in enumerate(lesson_titles, start=1):
                    raw_url = lesson_urls[i - 1].strip() if i <= len(lesson_urls) else ''
                    url = raw_url if raw_url else f'custom://manual/{uuid.uuid4()}'
                    to_create.append(Lesson(
                        key_stage=key_stage,
                        subject_name=subject_name,
                        programme_slug='custom',
                        year=child.school_year,
                        unit_slug='manual',
                        unit_title=unit_title,
                        lesson_number=i,
                        lesson_title=title,
                        lesson_url=url,
                        is_custom=True,
                        created_by=request.user,
                        custom_group=group,
                    ))
                Lesson.objects.bulk_create(to_create, ignore_conflicts=True)
                messages.success(
                    request,
                    f'{len(to_create)} lessons created for "{subject_name}". '
                    'Now enrol it and choose its days.'
                )
                return redirect('scheduler:subject_selection', child_id=child.pk)

        # ── TAB 3: CSV upload ─────────────────────────────────────────────────
        elif tab == 'csv':
            subject_name = request.POST.get('csv_subject_name', '').strip()
            key_stage    = request.POST.get('csv_key_stage', 'Custom').strip() or 'Custom'
            csv_file     = request.FILES.get('csv_file')
            if not subject_name:
                messages.error(request, 'Please enter a subject name.')
            elif not csv_file:
                messages.error(request, 'Please upload a CSV file.')
            else:
                try:
                    decoded = csv_file.read().decode('utf-8-sig')
                    reader = csv.DictReader(io.StringIO(decoded))
                    group = CustomSubjectGroup.objects.create(
                        parent=request.user,
                        subject_name=subject_name,
                        year=child.school_year,
                    )
                    to_create = []
                    for i, row in enumerate(reader, start=1):
                        title = (row.get('lesson_title') or '').strip()
                        if not title:
                            continue
                        unit = (row.get('unit_title') or subject_name).strip()
                        raw_url = (row.get('lesson_url') or '').strip()
                        url = raw_url if raw_url else f'custom://csv/{uuid.uuid4()}'
                        try:
                            lesson_num = int(row.get('lesson_number') or i)
                        except (ValueError, TypeError):
                            lesson_num = i
                        to_create.append(Lesson(
                            key_stage=key_stage,
                            subject_name=subject_name,
                            programme_slug='custom',
                            year=child.school_year,
                            unit_slug='csv',
                            unit_title=unit,
                            lesson_number=lesson_num,
                            lesson_title=title,
                            lesson_url=url,
                            is_custom=True,
                            created_by=request.user,
                            custom_group=group,
                        ))
                    if not to_create:
                        group.delete()
                        messages.error(request, 'No valid rows found. Check the lesson_title column.')
                    else:
                        Lesson.objects.bulk_create(to_create, ignore_conflicts=True)
                        messages.success(
                            request,
                            f'{len(to_create)} lessons created from CSV for "{subject_name}". '
                            'Now enrol it and choose its days.'
                        )
                        return redirect('scheduler:subject_selection', child_id=child.pk)
                except Exception:
                    messages.error(request, 'Could not parse the CSV. Check the file format.')

    return render(request, 'scheduler/custom_subject.html', {
        'child': child,
        'all_years': all_years,
        'year_subjects_json': json.dumps(year_subjects),
        'key_stages': key_stages,
        'child_year': child.school_year,
    })


@role_required('parent')
def schedule_edit_view(request, child_id):
    """Schedule editor: view, add, move, and delete individual ScheduledLesson rows.

    GET: lists all ScheduledLesson rows for the child grouped by date, with
    controls to delete individual rows or clear all rows for a subject.

    POST actions (via hidden ``action`` field):
    * ``delete_lesson`` — remove one ScheduledLesson by ``lesson_id``
    * ``delete_subject`` — remove all ScheduledLessons for an EnrolledSubject
    * ``clear_all`` — remove all ScheduledLessons for this child
    * ``move_lesson`` — change the ``scheduled_date`` of one ScheduledLesson
    """
    child = get_object_or_404(Child, pk=child_id, parent=request.user)

    if request.method == 'POST':
        action = request.POST.get('action', '')

        if action == 'delete_lesson':
            sl_id = request.POST.get('lesson_id')
            ScheduledLesson.objects.filter(pk=sl_id, child=child).delete()
            messages.success(request, 'Lesson removed from schedule.')

        elif action == 'delete_subject':
            es_id = request.POST.get('enrolled_subject_id')
            ScheduledLesson.objects.filter(enrolled_subject_id=es_id, child=child).delete()
            messages.success(request, 'All lessons for that subject removed.')

        elif action == 'clear_all':
            count, _ = child.scheduled_lessons.all().delete()
            messages.success(request, f'Schedule cleared — {count} lessons removed.')

        elif action == 'move_lesson':
            sl_id   = request.POST.get('lesson_id')
            new_date = request.POST.get('new_date', '').strip()
            try:
                parsed = datetime.date.fromisoformat(new_date)
                ScheduledLesson.objects.filter(pk=sl_id, child=child).update(scheduled_date=parsed)
                messages.success(request, 'Lesson rescheduled.')
            except (ValueError, TypeError):
                messages.error(request, 'Invalid date — use YYYY-MM-DD format.')

        return redirect('scheduler:schedule_edit', child_id=child.pk)

    # GET: group lessons by date
    scheduled = (
        child.scheduled_lessons
        .select_related('lesson', 'enrolled_subject')
        .order_by('scheduled_date', 'order_on_day')
    )

    # Group by date for template rendering
    from itertools import groupby
    grouped_schedule = []
    for date, group in groupby(scheduled, key=lambda sl: sl.scheduled_date):
        grouped_schedule.append({
            'date': date,
            'lessons': list(group),
        })

    enrolled_subjects = child.enrolled_subjects.filter(is_active=True)
    total = child.scheduled_lessons.count()

    return render(request, 'scheduler/schedule_edit.html', {
        'child': child,
        'grouped_schedule': grouped_schedule,
        'enrolled_subjects': enrolled_subjects,
        'total': total,
    })


@role_required('parent')
def manage_vacations_view(request, child_id):
    """List all vacations for a child and provide an inline add form."""
    from scheduler.models import Vacation
    child = get_object_or_404(Child, pk=child_id, parent=request.user)
    vacations = child.vacations.all()
    return render(request, 'scheduler/manage_vacations.html', {
        'child': child,
        'vacations': vacations,
    })


@role_required('parent')
def add_vacation_view(request, child_id):
    """Create a new vacation for a child via POST."""
    from scheduler.models import Vacation
    child = get_object_or_404(Child, pk=child_id, parent=request.user)

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        start_date_raw = request.POST.get('start_date', '').strip()
        end_date_raw = request.POST.get('end_date', '').strip()

        errors = []
        if not name:
            errors.append('Vacation name is required.')
        start_date = end_date = None
        try:
            start_date = datetime.date.fromisoformat(start_date_raw)
        except ValueError:
            errors.append('Start date is invalid.')
        try:
            end_date = datetime.date.fromisoformat(end_date_raw)
        except ValueError:
            errors.append('End date is invalid.')
        if start_date and end_date and end_date < start_date:
            errors.append('End date must be on or after start date.')

        if errors:
            for e in errors:
                messages.error(request, e)
        else:
            Vacation.objects.create(
                child=child,
                name=name,
                start_date=start_date,
                end_date=end_date,
            )
            messages.success(request, f'Vacation "{name}" added.')

    return redirect('scheduler:manage_vacations', child_id=child.pk)


@role_required('parent')
def delete_vacation_view(request, vacation_id):
    """Delete a vacation via POST (ownership verified via child.parent)."""
    from scheduler.models import Vacation
    vacation = get_object_or_404(Vacation, pk=vacation_id)
    child = vacation.child
    if child.parent_id != request.user.pk:
        return HttpResponseForbidden('You do not own this vacation.')
    if request.method == 'POST':
        vacation.delete()
        messages.success(request, 'Vacation deleted.')
    return redirect('scheduler:manage_vacations', child_id=child.pk)
