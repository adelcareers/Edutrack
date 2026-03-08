"""Role-based access control decorators for EduTrack views.

Usage example::

    from accounts.decorators import role_required

    @role_required('parent')
    def my_parent_view(request):
        ...
"""

import functools
from django.shortcuts import redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required


def role_required(role):
    """Decorator factory that restricts a view to users with a specific role.

    Behaviour:
    - Unauthenticated users are redirected to the login page with a ``next``
      parameter so they return to the intended URL after signing in.
    - Authenticated users whose role does not match ``role`` are redirected
      to the homepage with an error message explaining the restriction.
    - Authenticated users with the correct role proceed to the view normally.

    Usage::

        @role_required('parent')
        def parent_dashboard(request):
            ...

        @role_required('student')
        def student_calendar(request):
            ...

    Args:
        role (str): The required role string — one of ``'parent'``,
            ``'student'``, or ``'admin'``.

    Returns:
        Callable: A view decorator.
    """
    def decorator(view_func):
        @login_required
        @functools.wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            try:
                user_role = request.user.profile.role
            except AttributeError:
                # UserProfile does not exist — treat as wrong role
                user_role = None

            if user_role != role:
                messages.error(
                    request,
                    f"That page is only accessible to {role} accounts."
                )
                return redirect('home')

            return view_func(request, *args, **kwargs)

        return _wrapped
    return decorator
