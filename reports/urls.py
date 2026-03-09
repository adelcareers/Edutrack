from django.urls import path

from . import views

app_name = 'reports'

urlpatterns = [
    path('reports/create/<int:child_id>/', views.create_report_view, name='create_report'),
]
