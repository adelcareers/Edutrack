from django.urls import path

from . import views

app_name = 'tracker'

urlpatterns = [
    path('calendar/', views.calendar_view, name='calendar'),
    path('calendar/<int:year>/<int:week>/', views.calendar_view, name='calendar_week'),
]
