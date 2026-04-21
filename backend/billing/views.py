"""Billing stub views — Phase 5 will fill in Stripe checkout/webhooks."""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from orgs.permissions import get_user_org
from .models import OrganizationBilling, PlanTier


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_billing(request):
    """Return the current org's billing status (creates default Free row if missing)."""
    org = get_user_org(request.user)
    if not org:
        return Response({'has_organization': False})

    billing, _ = OrganizationBilling.objects.get_or_create(
        organization=org,
        defaults={'plan': PlanTier.FREE, 'monthly_generation_quota': 10},
    )

    return Response({
        'has_organization': True,
        'plan': billing.plan,
        'is_active': billing.is_active,
        'is_trial': billing.is_trial,
        'trial_ends_at': billing.trial_ends_at,
        'monthly_generation_quota': billing.monthly_generation_quota,
        'generations_used_this_period': billing.generations_used_this_period,
        'has_quota_remaining': billing.has_quota_remaining(),
    })
