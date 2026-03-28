from django.urls import path

from . import views

app_name = "planning"

urlpatterns = [
    path("plan/", views.plan_sessions_view, name="plan_sessions"),
    path("plan/<int:course_id>/", views.plan_course_view, name="plan_course"),
    path("plan/<int:course_id>/oak_schedule/", views.initiate_oak_scheduling_view, name="oak_schedule"),
]
