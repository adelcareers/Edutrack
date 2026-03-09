from django.urls import path

from . import views

app_name = 'tracker'

urlpatterns = [
    path('calendar/', views.calendar_view, name='calendar'),
    path('calendar/<int:year>/<int:week>/', views.calendar_view, name='calendar_week'),
    path('lessons/<int:scheduled_id>/detail/', views.lesson_detail_view, name='lesson_detail'),
    path('lessons/<int:scheduled_id>/update/', views.update_lesson_status_view, name='lesson_update'),
    path('lessons/<int:scheduled_id>/mastery/', views.update_mastery_view, name='lesson_mastery'),
]
