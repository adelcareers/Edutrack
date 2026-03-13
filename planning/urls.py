from django.urls import path

from . import views

app_name = 'planning'

urlpatterns = [
    path('plan/', views.plan_sessions_view, name='plan_sessions'),
    path('plan/<int:course_id>/', views.plan_course_view, name='plan_course'),
]
