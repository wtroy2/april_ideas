"""Theme views — list system + own-org themes, create custom org themes, fork."""

import logging
from copy import deepcopy

from django.db.models import Q
from django.shortcuts import get_object_or_404

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from orgs.permissions import get_user_org, IsOrgEditor

from .models import Theme
from .serializers import ThemeSerializer, CreateThemeSerializer

logger = logging.getLogger('themes')


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_themes(request):
    """List system themes + the current org's custom themes."""
    org = get_user_org(request.user)
    qs = Theme.objects.filter(is_active=True).filter(
        Q(organization__isnull=True) | Q(organization=org)
    )
    return Response(ThemeSerializer(qs, many=True).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def theme_detail(request, theme_uuid):
    org = get_user_org(request.user)
    theme = get_object_or_404(Theme, uuid=theme_uuid)
    if theme.organization and theme.organization != org:
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
    return Response(ThemeSerializer(theme).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsOrgEditor])
def create_theme(request):
    org = get_user_org(request.user)
    serializer = CreateThemeSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    theme = serializer.save(organization=org)
    return Response(ThemeSerializer(theme).data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsOrgEditor])
def fork_theme(request, theme_uuid):
    """Make an editable copy of a system (or another) theme into the current org."""
    org = get_user_org(request.user)
    source = get_object_or_404(Theme, uuid=theme_uuid)
    if source.organization and source.organization != org:
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

    new_slug = source.slug
    counter = 1
    while Theme.objects.filter(organization=org, slug=new_slug).exists():
        counter += 1
        new_slug = f'{source.slug}-{counter}'

    forked = Theme.objects.create(
        organization=org,
        name=f'{source.name} (custom)',
        slug=new_slug,
        description=source.description,
        cover_emoji=source.cover_emoji,
        shot_style=source.shot_style,
        music_vibe=source.music_vibe,
        prompt_template=source.prompt_template,
        caption_template=source.caption_template,
        default_scenarios=deepcopy(source.default_scenarios),
        tags=deepcopy(source.tags),
        is_active=True,
    )
    return Response(ThemeSerializer(forked).data, status=status.HTTP_201_CREATED)


@api_view(['PATCH', 'DELETE'])
@permission_classes([IsAuthenticated, IsOrgEditor])
def update_or_delete_theme(request, theme_uuid):
    org = get_user_org(request.user)
    theme = get_object_or_404(Theme, uuid=theme_uuid, organization=org)

    if request.method == 'DELETE':
        theme.is_active = False
        theme.save(update_fields=['is_active', 'updated_at'])
        return Response(status=status.HTTP_204_NO_CONTENT)

    # PATCH
    serializer = CreateThemeSerializer(theme, data=request.data, partial=True)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    serializer.save()
    return Response(ThemeSerializer(theme).data)
