"""Views for the scheduler app."""

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.models import User
from django.http import HttpResponseForbidden

from django.db.models import Count

from accounts.decorators import role_required
from accounts.forms import StudentCreationForm
from accounts.models import UserProfile
from curriculum.models import Lesson
from scheduler.forms import ChildForm
from scheduler.models import Child, EnrolledSubject

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
    """Display all active children belonging to the logged-in parent."""
    children = Child.objects.filter(parent=request.user, is_active=True)
    return render(request, 'scheduler/child_list.html', {'children': children})


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

    return render(request, 'scheduler/subject_selection.html', {
        'child': child,
        'grouped': grouped,
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
