from django.urls import path
from . import views

urlpatterns = [
    path('', views.list_themes, name='list_themes'),
    path('create/', views.create_theme, name='create_theme'),
    path('<uuid:theme_uuid>/', views.theme_detail, name='theme_detail'),
    path('<uuid:theme_uuid>/fork/', views.fork_theme, name='fork_theme'),
    path('<uuid:theme_uuid>/update/', views.update_or_delete_theme, name='update_or_delete_theme'),
]
