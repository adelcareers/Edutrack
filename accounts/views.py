"""Views for the accounts app — registration, login, logout, profile."""

from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.views import LoginView
from django.contrib import messages

from .forms import CustomUserCreationForm
from .models import ParentSettings, UserProfile
from accounts.decorators import role_required
from courses.models import (
    Course,
    GlobalAssignmentType,
    GLOBAL_ASSIGNMENT_DEFAULTS,
    sync_course_assignment_types_from_global,
)


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


def _get_or_create_parent_settings(user):
    settings, _ = ParentSettings.objects.get_or_create(user=user)
    return settings


def _seed_global_assignment_types(user):
    if GlobalAssignmentType.objects.filter(parent=user).exists():
        return
    to_create = [
        GlobalAssignmentType(
            parent=user,
            name=name,
            color=color,
            order=idx,
        )
        for idx, (name, color) in enumerate(GLOBAL_ASSIGNMENT_DEFAULTS)
    ]
    GlobalAssignmentType.objects.bulk_create(to_create)


def _save_global_assignment_types(request, user):
    indices = set()
    for key in request.POST:
        if key.startswith('at_name_'):
            try:
                idx = int(key.split('_')[-1])
            except ValueError:
                continue
            indices.add(idx)

    seen_ids = []
    for idx in sorted(indices):
        name = request.POST.get(f'at_name_{idx}', '').strip()
        color = request.POST.get(f'at_color_{idx}', '').strip() or '#9ca3af'
        is_hidden = request.POST.get(f'at_hidden_{idx}') == 'on'
        delete_flag = request.POST.get(f'at_delete_{idx}') == '1'
        at_id = request.POST.get(f'at_id_{idx}', '').strip()

        if delete_flag:
            if at_id:
                GlobalAssignmentType.objects.filter(pk=at_id, parent=user).delete()
            continue

        if not name:
            continue

        if at_id:
            GlobalAssignmentType.objects.filter(pk=at_id, parent=user).update(
                name=name,
                color=color,
                is_hidden=is_hidden,
                order=idx,
            )
            seen_ids.append(int(at_id))
        else:
            at = GlobalAssignmentType.objects.create(
                parent=user,
                name=name,
                color=color,
                is_hidden=is_hidden,
                order=idx,
            )
            seen_ids.append(at.pk)

    # Normalize ordering for all remaining types
    remaining = (
        GlobalAssignmentType.objects
        .filter(parent=user)
        .order_by('order', 'name')
    )
    for idx, at in enumerate(remaining):
        if at.order != idx:
            at.order = idx
            at.save(update_fields=['order'])


@role_required('parent')
def settings_view(request):
    settings = _get_or_create_parent_settings(request.user)
    _seed_global_assignment_types(request.user)

    if request.method == 'POST':
        first_day_raw = request.POST.get('first_day_of_week', str(settings.first_day_of_week))
        try:
            first_day = int(first_day_raw)
        except ValueError:
            first_day = settings.first_day_of_week

        valid_days = {choice[0] for choice in ParentSettings.WEEKDAY_CHOICES}
        settings.first_day_of_week = first_day if first_day in valid_days else settings.first_day_of_week
        settings.show_empty_assignments = request.POST.get('show_empty_assignments') == 'on'
        settings.save(update_fields=['first_day_of_week', 'show_empty_assignments'])

        _save_global_assignment_types(request, request.user)
        for course in Course.objects.filter(parent=request.user):
            sync_course_assignment_types_from_global(course)
        messages.success(request, 'Settings saved.')
        return redirect('accounts:settings')

    assignment_types = (
        GlobalAssignmentType.objects
        .filter(parent=request.user)
        .order_by('order', 'name')
    )

    return render(request, 'accounts/settings.html', {
        'settings': settings,
        'weekday_choices': ParentSettings.WEEKDAY_CHOICES,
        'assignment_types': assignment_types,
    })
