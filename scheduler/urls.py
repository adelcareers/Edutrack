"""URL configuration for the scheduler app."""

from django.urls import path

from . import views

app_name = "scheduler"

from django.views.generic import RedirectView

urlpatterns = [
    # /dashboard/ kept as a redirect so any old bookmarks still work
    path(
        "dashboard/",
        RedirectView.as_view(pattern_name="scheduler:child_list", permanent=True),
        name="parent_dashboard",
    ),
    path("children/", views.child_list_view, name="child_list"),
    path("children/new/", views.child_new_view, name="child_new"),
    path(
        "children/<int:child_id>/",
        views.child_detail_view,
        name="child_detail",
    ),
    path(
        "children/<int:child_id>/delete/",
        views.delete_child_view,
        name="delete_child",
    ),
    path(
        "children/<int:child_id>/create-login/",
        views.create_student_login_view,
        name="create_student_login",
    ),
    path(
        "children/<int:child_id>/subjects/",
        views.subject_selection_view,
        name="subject_selection",
    ),
    path(
        "children/<int:child_id>/subjects/custom/",
        views.custom_subject_view,
        name="custom_subject",
    ),
    path(
        "children/<int:child_id>/subjects/days/",
        views.schedule_days_view,
        name="schedule_days",
    ),
    path(
        "children/<int:child_id>/generate/",
        views.generate_schedule_view,
        name="generate_schedule",
    ),
    path(
        "children/<int:child_id>/schedule/",
        views.schedule_edit_view,
        name="schedule_edit",
    ),
    path(
        "children/<int:child_id>/vacations/",
        views.manage_vacations_view,
        name="manage_vacations",
    ),
    path(
        "children/<int:child_id>/vacations/add/",
        views.add_vacation_view,
        name="add_vacation",
    ),
    path(
        "vacations/<int:vacation_id>/delete/",
        views.delete_vacation_view,
        name="delete_vacation",
    ),
]
