from django.urls import path
from . import views

urlpatterns = [
    path('my/', views.my_billing, name='my_billing'),
]
