"""URL configuration for the scheduler app."""

from django.urls import path
from . import views

app_name = 'scheduler'

urlpatterns = [
    path(
        'children/<int:child_id>/create-login/',
        views.create_student_login_view,
        name='create_student_login',
    ),
]
