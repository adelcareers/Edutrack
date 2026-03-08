"""Views for the accounts app — registration, login, logout, profile."""

from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib import messages

from .forms import CustomUserCreationForm
from .models import UserProfile


def register_view(request):
    """Handle parent account registration.

    GET:  Render a blank registration form.
    POST: Validate the form; on success create the User, create a linked
          UserProfile with role='parent', log the user in, and redirect
          to the home page with a welcome message.
    """
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            UserProfile.objects.create(user=user, role='parent')
            login(request, user)
            messages.success(
                request,
                "Welcome to EduTrack! Your parent account is ready."
            )
            return redirect('home')
    else:
        form = CustomUserCreationForm()

    return render(request, 'accounts/register.html', {'form': form})
