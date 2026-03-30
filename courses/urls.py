from django.urls import path

from . import views

app_name = "courses"

urlpatterns = [
    # Course CRUD
    path("courses/", views.course_list_view, name="course_list"),
    path("courses/archived/", views.archived_courses_view, name="archived_courses"),
    path(
        "courses/archived/<int:archive_id>/",
        views.archived_course_detail_view,
        name="archived_course_detail",
    ),
    path("courses/new/", views.course_new_view, name="course_new"),
    path("courses/<int:course_id>/", views.course_detail_view, name="course_detail"),
    path("courses/<int:course_id>/edit/", views.course_edit_view, name="course_edit"),
    path(
        "courses/<int:course_id>/archive/",
        views.course_archive_view,
        name="course_archive",
    ),
    path(
        "courses/<int:course_id>/delete/",
        views.course_delete_view,
        name="course_delete",
    ),
    path(
        "courses/<int:course_id>/export/",
        views.course_export_view,
        name="course_export",
    ),
    # Enrollment
    path(
        "courses/<int:course_id>/enroll/",
        views.enroll_student_view,
        name="course_enroll",
    ),
    path(
        "courses/enrollments/<int:enrollment_id>/unenroll/",
        views.unenroll_student_view,
        name="enrollment_unenroll",
    ),
    path(
        "courses/enrollments/<int:enrollment_id>/complete/",
        views.complete_enrollment_view,
        name="enrollment_complete",
    ),
    path(
        "courses/enrollments/<int:enrollment_id>/reactivate/",
        views.reactivate_enrollment_view,
        name="enrollment_reactivate",
    ),
    # Subject AJAX endpoints
    path("courses/subjects/", views.subject_list_view, name="subject_list"),
    path("courses/subjects/create/", views.subject_create_view, name="subject_create"),
    # CourseSubjectConfig management
    path(
        "courses/subject-config/<int:config_id>/deactivate/",
        views.subject_config_soft_delete_view,
        name="subject_config_deactivate",
    ),
    path(
        "courses/subject-config/<int:config_id>/delete/",
        views.subject_config_hard_delete_view,
        name="subject_config_delete",
    ),
]
