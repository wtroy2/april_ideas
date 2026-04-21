"""Permission helpers for org-scoped views."""

from rest_framework.permissions import BasePermission
from .models import OrganizationMember, MemberRole


def get_user_org(user):
    """Return the user's Organization, or None."""
    if hasattr(user, 'organization_membership'):
        return user.organization_membership.organization
    return None


def get_user_role(user):
    """Return the user's role in their org, or None."""
    if hasattr(user, 'organization_membership'):
        return user.organization_membership.role
    return None


class IsOrgMember(BasePermission):
    """User must belong to an org."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and hasattr(request.user, 'organization_membership')


class IsOrgAdmin(BasePermission):
    """User must be an admin in their org."""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return get_user_role(request.user) == MemberRole.ADMIN


class IsOrgEditor(BasePermission):
    """User must be admin or editor."""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return get_user_role(request.user) in [MemberRole.ADMIN, MemberRole.EDITOR]
