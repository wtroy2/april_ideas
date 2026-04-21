from django.urls import path
from . import views

urlpatterns = [
    path('', views.list_stories, name='list_stories'),
    path('create/', views.create_story, name='create_story'),
    path('<uuid:story_uuid>/', views.story_detail, name='story_detail'),
    path('<uuid:story_uuid>/update/', views.update_story, name='update_story'),
    path('<uuid:story_uuid>/delete/', views.delete_story, name='delete_story'),
    path('<uuid:story_uuid>/replan/', views.replan_story, name='replan_story'),

    path('<uuid:story_uuid>/scenes/add/', views.add_scene, name='add_scene'),
    path('<uuid:story_uuid>/scenes/<int:scene_id>/', views.update_scene, name='update_scene'),
    path('<uuid:story_uuid>/scenes/<int:scene_id>/delete/', views.delete_scene, name='delete_scene'),
    path('<uuid:story_uuid>/scenes/<int:scene_id>/generate/', views.generate_scene, name='generate_scene'),
    path('<uuid:story_uuid>/scenes/<int:scene_id>/pick/<uuid:generation_uuid>/', views.pick_take, name='pick_take'),

    path('<uuid:story_uuid>/generate-all/', views.generate_all_scenes, name='generate_all_scenes'),
    path('<uuid:story_uuid>/stitch/', views.stitch_story_view, name='stitch_story'),
]
