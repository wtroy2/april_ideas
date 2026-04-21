from django.urls import path
from . import views

urlpatterns = [
    path('summary/', views.request_summary, name='analytics_request_summary'),
]
