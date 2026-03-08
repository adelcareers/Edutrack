"""Views for the accounts app — registration, login, logout, profile."""

from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.views import LoginView
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


class CustomLoginView(LoginView):
    """Login view using a custom template.

    Extends Django's built-in LoginView so all authentication logic
    (rate limiting awareness, next-param handling, etc.) is inherited.
    The template is swapped to match the EduTrack design system.
    """

    template_name = 'accounts/login.html'

    def dispatch(self, request, *args, **kwargs):
        """Redirect already-authenticated users away from the login page."""
        if request.user.is_authenticated:
            return redirect('home')
        return super().dispatch(request, *args, **kwargs)


def logout_view(request):
    """Log the current user out and redirect to the homepage.

    Accepts POST only — a GET request to this URL returns 405. Using POST
    prevents accidental or malicious logout via a crafted GET link.
    """
    if request.method == 'POST':
        logout(request)
        messages.info(request, "You have been logged out.")
        return redirect('home')
    return redirect('home')
