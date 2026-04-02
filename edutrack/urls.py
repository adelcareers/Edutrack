"""Project URL configuration, including the logged-out marketing landing page."""

from pathlib import Path

from django.contrib import admin
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import include, path

_LANDING_HTML_PATH = (
    Path(__file__).resolve().parent.parent / "landing" / "index.html"
)


def landing_page(request):
    """Serve the canonical landing page for anonymous visitors."""
    return HttpResponse(
        _LANDING_HTML_PATH.read_text(), content_type="text/html"
    )


def root_redirect(request):
    """Redirect authenticated users to their role's landing page.

    - parent/teacher/student → /home/
    - others / unauthenticated → landing page
    """
    if request.user.is_authenticated:
        try:
            role = request.user.profile.role
        except AttributeError:
            role = None
        if role in {"parent", "student", "teacher"}:
            return redirect("tracker:home_assignments")
    return landing_page(request)


urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("", include("scheduler.urls")),
    path("", include("tracker.urls")),
    path("", include("reports.urls")),
    path("", include("courses.urls")),
    path("", include("planning.urls")),
    path("", root_redirect, name="home"),
]
