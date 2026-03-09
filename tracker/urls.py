from django.urls import path

from . import views

app_name = 'tracker'

urlpatterns = [
    path('calendar/', views.calendar_view, name='calendar'),
    path('calendar/<int:year>/<int:week>/', views.calendar_view, name='calendar_week'),
    path('lessons/<int:scheduled_id>/detail/', views.lesson_detail_view, name='lesson_detail'),
    path('lessons/<int:scheduled_id>/update/', views.update_lesson_status_view, name='lesson_update'),
    path('lessons/<int:scheduled_id>/mastery/', views.update_mastery_view, name='lesson_mastery'),
    path('lessons/<int:scheduled_id>/notes/', views.save_notes_view, name='lesson_notes'),
    path('lessons/<int:scheduled_id>/reschedule/', views.reschedule_lesson_view, name='lesson_reschedule'),
    path('parent/calendar/<int:child_id>/', views.parent_calendar_view, name='parent_calendar'),
    path('parent/calendar/<int:child_id>/<int:year>/<int:week>/', views.parent_calendar_view, name='parent_calendar_week'),
]
