from django.urls import path
from . import views

urlpatterns = [
    path('', views.list_assets, name='list_assets'),
    path('audio/', views.list_audio, name='list_audio'),
    path('audio/upload/', views.upload_audio, name='upload_audio'),
    path('<uuid:asset_uuid>/', views.asset_detail, name='asset_detail'),
    path('<uuid:asset_uuid>/delete/', views.delete_asset, name='delete_asset'),
]
