"""Views for the scheduler app."""

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.models import User
from django.http import HttpResponseForbidden

from accounts.decorators import role_required
from accounts.forms import StudentCreationForm
from accounts.models import UserProfile
from scheduler.forms import ChildForm
from scheduler.models import Child


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
