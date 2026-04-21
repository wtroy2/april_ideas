from django.urls import path
from . import views

urlpatterns = [
    path('', views.list_subjects, name='list_subjects'),
    path('create/', views.create_subject, name='create_subject'),
    path('<uuid:subject_uuid>/', views.subject_detail, name='subject_detail'),
    path('<uuid:subject_uuid>/photos/', views.upload_subject_photos, name='upload_subject_photos'),
    path('<uuid:subject_uuid>/photos/<int:photo_id>/', views.delete_subject_photo, name='delete_subject_photo'),
    path('<uuid:subject_uuid>/photos/<int:photo_id>/primary/', views.set_primary_photo, name='set_primary_photo'),
    path('<uuid:subject_uuid>/regenerate-description/', views.regenerate_description, name='regenerate_description'),
]
