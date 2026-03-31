"""Student login creation views."""

from django.contrib import messages
from django.contrib.auth.models import User
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import role_required
from accounts.forms import StudentCreationForm
from accounts.models import UserProfile
from scheduler.models import Child


@role_required("parent")
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
            f"(email: {child.student_user.email or child.student_user.username}).",
        )
        return redirect("home")

    if request.method == "POST":
        form = StudentCreationForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"].lower().strip()
            password = form.cleaned_data["password1"]
            student_user = User.objects.create_user(
                username=email,
                email=email,
                password=password,
            )
            UserProfile.objects.create(user=student_user, role="student")
            child.student_user = student_user
            child.save()
            messages.success(
                request,
                f"Login created for {child.first_name}. "
                f'They can now sign in as "{email}".',
            )
            return redirect("home")
    else:
        form = StudentCreationForm()

    return render(
        request,
        "scheduler/create_student_login.html",
        {
            "form": form,
            "child": child,
        },
    )
