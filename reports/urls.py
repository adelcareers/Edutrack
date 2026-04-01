from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("gradebooks/", views.gradebook_list_view, name="gradebook_list"),
    path(
        "gradebooks/child/<int:child_id>/",
        views.gradebook_child_detail_view,
        name="gradebook_child_detail",
    ),
    path(
        "gradebooks/assignments/<int:assignment_id>/status/",
        views.gradebook_assignment_status_view,
        name="gradebook_assignment_status",
    ),
    path(
        "gradebooks/assignments/<int:assignment_id>/comments/",
        views.gradebook_assignment_comment_create_view,
        name="gradebook_assignment_comment_create",
    ),
    path(
        "gradebooks/assignments/<int:assignment_id>/submissions/",
        views.gradebook_assignment_submission_upload_view,
        name="gradebook_assignment_submission_upload",
    ),
    path(
        "gradebooks/transcript/<int:child_id>/",
        views.gradebook_transcript_view,
        name="gradebook_transcript",
    ),
    path(
        "gradebooks/<int:enrollment_id>/",
        views.gradebook_detail_view,
        name="gradebook_detail",
    ),
    path(
        "reports/create/<int:child_id>/", views.create_report_view, name="create_report"
    ),
    path("reports/<int:pk>/", views.report_detail_view, name="report_detail"),
    path("reports/share/<uuid:token>/", views.token_report_view, name="shared_report"),
    path("reports/tracking/", views.tracking_overview_view, name="tracking_overview"),
]
