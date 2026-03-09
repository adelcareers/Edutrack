"""URL configuration for the scheduler app."""

from django.urls import path
from . import views

app_name = 'scheduler'

urlpatterns = [
    path('dashboard/', views.parent_dashboard_view, name='parent_dashboard'),
    path('children/', views.child_list_view, name='child_list'),
    path('children/add/', views.add_child_view, name='add_child'),
    path(
        'children/<int:child_id>/create-login/',
        views.create_student_login_view,
        name='create_student_login',
    ),
    path(
        'children/<int:child_id>/subjects/',
        views.subject_selection_view,
        name='subject_selection',
    ),
    path(
        'children/<int:child_id>/generate/',
        views.generate_schedule_view,
        name='generate_schedule',
    ),
]
