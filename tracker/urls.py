from django.urls import path

from . import views

app_name = 'tracker'

urlpatterns = [
    path('calendar/', views.calendar_view, name='calendar'),
    path('calendar/<int:year>/<int:week>/', views.calendar_view, name='calendar_week'),
    path('calendar/export.ics', views.export_ical_view, name='export_ical'),
    path('lessons/<int:scheduled_id>/detail/', views.lesson_detail_view, name='lesson_detail'),
    path('lessons/<int:scheduled_id>/update/', views.update_lesson_status_view, name='lesson_update'),
    path('lessons/<int:scheduled_id>/mastery/', views.update_mastery_view, name='lesson_mastery'),
    path('lessons/<int:scheduled_id>/notes/', views.save_notes_view, name='lesson_notes'),
    path('lessons/<int:scheduled_id>/reschedule/', views.reschedule_lesson_view, name='lesson_reschedule'),
    path('lessons/<int:scheduled_id>/upload/', views.upload_evidence_view, name='lesson_upload'),
    path('assignments/<int:assignment_id>/detail/', views.assignment_detail_view, name='assignment_detail'),
    path('assignments/<int:assignment_id>/update/', views.update_assignment_status_view, name='assignment_update'),
    path('evidence/<int:file_id>/delete/', views.delete_evidence_view, name='evidence_delete'),
    path('parent/calendar/', views.parent_calendar_home_view, name='parent_calendar_home'),
    path('parent/calendar/<int:child_id>/', views.parent_calendar_view, name='parent_calendar'),
    path('parent/calendar/<int:child_id>/<int:year>/<int:week>/', views.parent_calendar_view, name='parent_calendar_week'),
    path('parent/calendar/<int:child_id>/export.ics', views.parent_export_ical_view, name='parent_export_ical'),
]
