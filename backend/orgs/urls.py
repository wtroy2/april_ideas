from django.urls import path
from . import views

urlpatterns = [
    # Organization
    path('my/', views.my_organizations, name='my_organizations'),
    path('create/', views.create_organization, name='create_organization'),
    path('<int:org_id>/', views.organization_detail, name='organization_detail'),

    # Members
    path('members/', views.list_members, name='list_members'),
    path('members/<int:member_id>/role/', views.update_member_role, name='update_member_role'),
    path('members/<int:member_id>/', views.remove_member, name='remove_member'),

    # Invitations
    path('invitations/', views.list_invitations, name='list_invitations'),
    path('invitations/create/', views.create_invitation, name='create_invitation'),
    path('invitations/<str:token>/', views.get_invitation, name='get_invitation'),
    path('invitations/<str:token>/accept/', views.accept_invitation, name='accept_invitation'),
    path('invitations/<int:invitation_id>/revoke/', views.revoke_invitation, name='revoke_invitation'),
]
