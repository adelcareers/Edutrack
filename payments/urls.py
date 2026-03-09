from django.urls import path
from . import views

app_name = 'payments'

urlpatterns = [
    path('payments/plans/', views.pricing_page_view, name='pricing'),
]