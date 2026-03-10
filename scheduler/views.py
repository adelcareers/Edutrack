"""Views for the scheduler app."""

import datetime
import json

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.models import User
from django.http import HttpResponseForbidden

from django.db.models import Count

from accounts.decorators import role_required
from accounts.forms import StudentCreationForm
from accounts.models import UserProfile
from curriculum.models import Lesson
from scheduler.forms import ChildForm, NewStudentModalForm
from scheduler.models import Child, EnrolledSubject, ScheduledLesson
from scheduler.services import generate_schedule

SUBJECT_COLOUR_PALETTE = [
    '#E63946', '#2A9D8F', '#E9C46A', '#F4A261', '#264653',
    '#8338EC', '#3A86FF', '#FB5607', '#FFBE0B', '#06D6A0',
]


@role_required('parent')
def add_child_view(request):
    """Allow a parent to add a child's profile.

    On successful submission the parent is forwarded to the subject selection
    page for the newly created child so the onboarding flow continues without
    interruption.
    """
    if request.method == 'POST':
        form = ChildForm(request.POST)
        if form.is_valid():
            child = form.save(commit=False)
            child.parent = request.user
            child.save()
            messages.success(
                request,
                f"{child.first_name} added! Now select their subjects.",
            )
            return redirect(f'/children/{child.pk}/subjects/')
    else:
        form = ChildForm()

    return render(request, 'scheduler/add_child.html', {'form': form})


@role_required('parent')
def child_list_view(request):
    """Display all active children and handle the 'New Student' modal form."""
    today = datetime.date.today()
    week_start = today - datetime.timedelta(days=today.weekday())
    week_end = week_start + datetime.timedelta(days=6)

    children = Child.objects.filter(parent=request.user, is_active=True)
    form = NewStudentModalForm()
    show_modal = False

    # Pre-load subjects grouped by year for the modal JS filter.
    # Structure: {"Year 5": [{"subject": "Art", "key_stage": "KS2"}, ...], ...}
    subjects_qs = (
        Lesson.objects
        .values('year', 'key_stage', 'subject_name')
        .distinct()
        .order_by('year', 'key_stage', 'subject_name')
    )
    subjects_by_year = {}
    for row in subjects_qs:
        subjects_by_year.setdefault(row['year'], []).append({
            'subject': row['subject_name'],
            'key_stage': row['key_stage'],
        })
    subjects_by_year_json = json.dumps(subjects_by_year)

    if request.method == 'POST' and 'add_student' in request.POST:
        form = NewStudentModalForm(request.POST, request.FILES)
        if form.is_valid():
            if today.month >= 9:
                academic_start = datetime.date(today.year, 9, 1)
            else:
                academic_start = datetime.date(today.year - 1, 9, 1)

            school_year = form.cleaned_data.get('school_year') or 'Year 1'
            child = Child(
                parent=request.user,
                first_name=form.cleaned_data['first_name'],
                school_year=school_year,
                birth_month=today.month,
                birth_year=today.year - 10,
                academic_year_start=academic_start,
            )
            if form.cleaned_data.get('photo'):
                child.photo = form.cleaned_data['photo']
            child.save()

            # Enrol any subjects ticked in the modal
            selected_subjects = request.POST.getlist('subjects')
            if selected_subjects:
                # Build a lookup: subject_name -> key_stage from the pre-loaded data
                subject_meta = {
                    row['subject_name']: row['key_stage']
                    for row in Lesson.objects
                    .filter(year=school_year)
                    .values('subject_name', 'key_stage')
                    .distinct()
                }
                for idx, subject_name in enumerate(selected_subjects):
                    EnrolledSubject.objects.create(
                        child=child,
                        subject_name=subject_name,
                        key_stage=subject_meta.get(subject_name, ''),
                        lessons_per_week=1,
                        colour_hex=SUBJECT_COLOUR_PALETTE[idx % len(SUBJECT_COLOUR_PALETTE)],
                    )
                messages.success(
                    request,
                    f"{child.first_name} added with {len(selected_subjects)} subject(s). "
                    f"Review and generate their schedule.",
                )
                return redirect('scheduler:generate_schedule', child_id=child.pk)
            else:
                messages.success(
                    request,
                    f"{child.first_name} added! Now select their subjects.",
                )
                return redirect('scheduler:subject_selection', child_id=child.pk)
        else:
            show_modal = True

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
        'form': form,
        'show_modal': show_modal,
        'subjects_by_year_json': subjects_by_year_json,
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


@role_required('parent')
def subject_selection_view(request, child_id):
    """Let a parent choose which subjects their child will study and set weekly pace.

    GET: builds a grouped context of all subjects available for the child's school
    year, ordered by key_stage then subject_name, with a total lesson count badge.

    POST: for every selected subject creates an ``EnrolledSubject`` record with a
    colour from the palette cycling by insertion index.  Enforces that at least
    one subject is ticked, then redirects to the schedule generation page.
    """
    child = get_object_or_404(Child, pk=child_id)

    if child.parent != request.user:
        return HttpResponseForbidden("You do not have permission to manage this child.")

    # Build grouped subject data: {key_stage: [{subject_name, total_lessons}, ...]}
    lessons_qs = (
        Lesson.objects
        .filter(year=child.school_year)
        .values('key_stage', 'subject_name')
        .annotate(total_lessons=Count('id'))
        .order_by('key_stage', 'subject_name')
    )

    grouped = {}
    for row in lessons_qs:
        grouped.setdefault(row['key_stage'], []).append({
            'subject_name': row['subject_name'],
            'total_lessons': row['total_lessons'],
        })

    if request.method == 'POST':
        selected_subjects = request.POST.getlist('subjects')
        if not selected_subjects:
            messages.error(request, "Please select at least one subject.")
            return render(request, 'scheduler/subject_selection.html', {
                'child': child,
                'grouped': grouped,
            })

        # Delete any existing enrolments before recreating (idempotent re-submission)
        child.enrolled_subjects.all().delete()

        to_create = []
        for index, subject_name in enumerate(selected_subjects):
            pace_key = f'pace_{subject_name}'
            try:
                pace = max(1, min(5, int(request.POST.get(pace_key, 1))))
            except (ValueError, TypeError):
                pace = 1

            key_stage = (
                Lesson.objects
                .filter(year=child.school_year, subject_name=subject_name)
                .values_list('key_stage', flat=True)
                .first() or ''
            )
            to_create.append(EnrolledSubject(
                child=child,
                subject_name=subject_name,
                key_stage=key_stage,
                lessons_per_week=pace,
                colour_hex=SUBJECT_COLOUR_PALETTE[index % len(SUBJECT_COLOUR_PALETTE)],
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
def parent_dashboard_view(request):
    """Show a dashboard summarising each child's schedule progress.

    For each active child the view computes:
    - ``total_scheduled`` — total ScheduledLesson rows for the child.
    - ``completed_this_week`` — lessons with a LessonLog status of 'complete'
      whose scheduled_date falls in the current ISO week (Mon–Sun).
    - ``total_complete`` — all completed lessons ever.
    - ``pct_complete`` — integer percentage of total lessons completed.

    If the parent has no children an empty-state prompt is shown instead.
    """
    today = datetime.date.today()
    # ISO week: Monday of the current week
    week_start = today - datetime.timedelta(days=today.weekday())
    week_end = week_start + datetime.timedelta(days=6)

    children = Child.objects.filter(parent=request.user, is_active=True)

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

    return render(request, 'scheduler/parent_dashboard.html', {
        'summaries': summaries,
    })
