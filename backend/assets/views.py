"""Asset views — list/detail + audio upload (subject photos upload via subjects app)."""

import logging

from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework import status

from orgs.permissions import get_user_org

from .models import Asset, AssetKind
from .serializers import AssetSerializer
from .services import ingest_audio_upload

logger = logging.getLogger('assets')


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_assets(request):
    """List assets for the current org. Optional ?kind=... filter."""
    org = get_user_org(request.user)
    if not org:
        return Response([])
    qs = Asset.objects.filter(organization=org)
    kind = request.query_params.get('kind')
    if kind:
        qs = qs.filter(kind=kind)
    return Response(AssetSerializer(qs[:200], many=True).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def asset_detail(request, asset_uuid):
    org = get_user_org(request.user)
    try:
        asset = Asset.objects.get(uuid=asset_uuid, organization=org)
    except Asset.DoesNotExist:
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
    return Response(AssetSerializer(asset).data)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_asset(request, asset_uuid):
    org = get_user_org(request.user)
    try:
        asset = Asset.objects.get(uuid=asset_uuid, organization=org)
    except Asset.DoesNotExist:
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
    asset.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_audio(request):
    """List uploaded music tracks for the current org."""
    org = get_user_org(request.user)
    if not org:
        return Response([])
    qs = Asset.objects.filter(organization=org, kind=AssetKind.AUDIO).order_by('-created_at')
    return Response(AssetSerializer(qs, many=True).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def upload_audio(request):
    """
    Upload a music track. Field name: `audio` (or `file`). Returns the new Asset.
    """
    org = get_user_org(request.user)
    if not org:
        return Response({'error': 'You must belong to an organization'},
                        status=status.HTTP_400_BAD_REQUEST)

    f = request.FILES.get('audio') or request.FILES.get('file')
    if not f:
        return Response({'error': 'No file provided (use field name "audio")'},
                        status=status.HTTP_400_BAD_REQUEST)

    if not (f.content_type or '').startswith('audio/'):
        return Response({'error': f'Unsupported content type: {f.content_type}'},
                        status=status.HTTP_400_BAD_REQUEST)

    try:
        asset = ingest_audio_upload(organization=org, user=request.user, uploaded_file=f)
    except Exception as e:
        logger.exception(f'audio upload failed: {e}')
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response(AssetSerializer(asset).data, status=status.HTTP_201_CREATED)
