"""
URL configuration for edutrack project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.shortcuts import redirect, render
from django.urls import include, path


def home(request):
    """Placeholder homepage view — shown to unauthenticated visitors."""
    return render(request, "home.html")


def root_redirect(request):
    """Redirect authenticated users to their role's landing page.

    - parent/teacher/student → /home/
    - others / unauthenticated → home page
    """
    if request.user.is_authenticated:
        try:
            role = request.user.profile.role
        except AttributeError:
            role = None
        if role in {"parent", "student", "teacher"}:
            return redirect("tracker:home_assignments")
    return render(request, "home.html")


urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("", include("scheduler.urls")),
    path("", include("tracker.urls")),
    path("", include("reports.urls")),
    path("", include("payments.urls")),
    path("", include("courses.urls")),
    path("", include("planning.urls")),
    path("", root_redirect, name="home"),
]
