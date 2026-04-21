from django.urls import path
from . import views

urlpatterns = [
    path('batches/', views.list_batches, name='list_batches'),
    path('batches/create/', views.create_batch, name='create_batch'),
    path('batches/<uuid:batch_uuid>/', views.batch_detail, name='batch_detail'),
    path('batches/<uuid:batch_uuid>/audio/', views.update_batch_audio, name='update_batch_audio'),
    path('batches/<uuid:batch_uuid>/remix/', views.remix_batch, name='remix_batch'),
    path('<uuid:generation_uuid>/regenerate/', views.regenerate, name='regenerate'),
    path('<uuid:generation_uuid>/cancel/', views.cancel_generation, name='cancel_generation'),
    path('<uuid:generation_uuid>/reset-to-raw/', views.reset_generation_to_raw, name='reset_generation_to_raw'),
]
