"""Organization views — function-based DRF (RateRail style)."""

import logging

from django.conf import settings
from django.shortcuts import get_object_or_404
from django.db import transaction

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import Organization, OrganizationMember, OrganizationInvitation, MemberRole
from .serializers import (
    OrganizationSerializer, CreateOrganizationSerializer,
    OrganizationMemberSerializer, OrganizationInvitationSerializer,
    CreateInvitationSerializer,
)
from .permissions import get_user_org, get_user_role, IsOrgAdmin

logger = logging.getLogger('auth_debug')


# --------------------------------------------------------------------------
# Organization CRUD
# --------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_organizations(request):
    """Get the org(s) the user belongs to. Returns a list (legacy frontend expects this shape)."""
    org = get_user_org(request.user)
    if not org:
        return Response([])
    return Response([OrganizationSerializer(org, context={'request': request}).data])


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def organization_detail(request, org_id):
    org = get_object_or_404(Organization, id=org_id)
    if get_user_org(request.user) != org:
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
    return Response(OrganizationSerializer(org, context={'request': request}).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_organization(request):
    """User creates their first organization (becomes admin)."""
    if hasattr(request.user, 'organization_membership'):
        return Response({'error': 'You already belong to an organization'},
                        status=status.HTTP_400_BAD_REQUEST)

    serializer = CreateOrganizationSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        org = serializer.save()
        OrganizationMember.objects.create(
            organization=org, user=request.user, role=MemberRole.ADMIN
        )
    return Response(OrganizationSerializer(org, context={'request': request}).data,
                    status=status.HTTP_201_CREATED)


# --------------------------------------------------------------------------
# Members
# --------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_members(request):
    org = get_user_org(request.user)
    if not org:
        return Response({'error': 'No organization'}, status=status.HTTP_404_NOT_FOUND)
    members = org.members.select_related('user').all()
    return Response(OrganizationMemberSerializer(members, many=True).data)


@api_view(['PATCH'])
@permission_classes([IsAuthenticated, IsOrgAdmin])
def update_member_role(request, member_id):
    member = get_object_or_404(OrganizationMember, id=member_id)
    if member.organization != get_user_org(request.user):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

    new_role = request.data.get('role')
    if new_role not in dict(MemberRole.choices):
        return Response({'error': 'Invalid role'}, status=status.HTTP_400_BAD_REQUEST)

    member.role = new_role
    member.save()
    return Response(OrganizationMemberSerializer(member).data)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, IsOrgAdmin])
def remove_member(request, member_id):
    member = get_object_or_404(OrganizationMember, id=member_id)
    if member.organization != get_user_org(request.user):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
    if member.user == request.user:
        return Response({'error': 'Cannot remove yourself'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        member.delete()
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    return Response({'message': 'Member removed'}, status=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------
# Invitations
# --------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_invitations(request):
    org = get_user_org(request.user)
    if not org:
        return Response([])
    invs = org.invitations.filter(is_used=False)
    return Response(OrganizationInvitationSerializer(invs, many=True).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsOrgAdmin])
def create_invitation(request):
    org = get_user_org(request.user)
    serializer = CreateInvitationSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    email = serializer.validated_data['email']
    role = serializer.validated_data['role']

    # Don't allow inviting an email that already has an account in another org
    from users.models import CustomUser
    existing = CustomUser.objects.filter(email__iexact=email).first()
    if existing and hasattr(existing, 'organization_membership'):
        return Response({'error': 'That email is already a member of another organization'},
                        status=status.HTTP_400_BAD_REQUEST)

    inv = OrganizationInvitation.objects.create(
        organization=org, email=email, role=role, created_by=request.user
    )
    inv.send_invitation_email(settings.REACT_BASE_URL)
    return Response(OrganizationInvitationSerializer(inv).data, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([AllowAny])
def get_invitation(request, token):
    """Public endpoint — invite recipient looks up their invite before registering."""
    try:
        inv = OrganizationInvitation.objects.select_related('organization').get(
            token=token, is_used=False
        )
    except OrganizationInvitation.DoesNotExist:
        return Response({'error': 'Invitation not found or already used'},
                        status=status.HTTP_404_NOT_FOUND)
    return Response(OrganizationInvitationSerializer(inv).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def accept_invitation(request, token):
    """Newly-registered user accepts an invitation — joins the org."""
    try:
        inv = OrganizationInvitation.objects.select_related('organization').get(
            token=token, is_used=False
        )
    except OrganizationInvitation.DoesNotExist:
        return Response({'error': 'Invitation not found'}, status=status.HTTP_404_NOT_FOUND)

    if hasattr(request.user, 'organization_membership'):
        return Response({'error': 'You already belong to an organization'},
                        status=status.HTTP_400_BAD_REQUEST)

    if request.user.email.lower() != inv.email.lower():
        return Response({'error': 'This invitation is for a different email address'},
                        status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        OrganizationMember.objects.create(
            organization=inv.organization, user=request.user, role=inv.role
        )
        inv.is_used = True
        inv.save(update_fields=['is_used'])

    return Response({'message': f'You joined {inv.organization.name}'})


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, IsOrgAdmin])
def revoke_invitation(request, invitation_id):
    inv = get_object_or_404(OrganizationInvitation, id=invitation_id)
    if inv.organization != get_user_org(request.user):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
    inv.delete()
    return Response({'message': 'Invitation revoked'}, status=status.HTTP_204_NO_CONTENT)
