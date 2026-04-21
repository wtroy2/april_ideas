"""
Subject views — CRUD + photo upload.

Pattern lifted from RateRail: function-based @api_view, IsAuthenticated by
default, all queries scoped to the current user's organization.
"""

import logging

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response

from core.jobs import run_job
from orgs.permissions import get_user_org
from assets.services import ingest_user_upload
from assets.models import AssetKind

from .models import Subject, SubjectPhoto
from .serializers import SubjectSerializer, CreateSubjectSerializer
from . import jobs

logger = logging.getLogger('subjects')


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_subjects(request):
    org = get_user_org(request.user)
    if not org:
        return Response([])
    qs = Subject.objects.filter(organization=org, is_archived=False).prefetch_related('subject_photos__asset')
    return Response(SubjectSerializer(qs, many=True).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_subject(request):
    org = get_user_org(request.user)
    if not org:
        return Response({'error': 'You must belong to an organization'},
                        status=status.HTTP_400_BAD_REQUEST)

    serializer = CreateSubjectSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    subject = serializer.save(organization=org, created_by=request.user)
    return Response(SubjectSerializer(subject).data, status=status.HTTP_201_CREATED)


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def subject_detail(request, subject_uuid):
    org = get_user_org(request.user)
    subject = get_object_or_404(Subject, uuid=subject_uuid, organization=org)

    if request.method == 'GET':
        return Response(SubjectSerializer(subject).data)

    if request.method == 'PATCH':
        # Allow editing name, species, kind, user_description, is_archived
        for field in ('name', 'species', 'kind', 'user_description', 'is_archived'):
            if field in request.data:
                setattr(subject, field, request.data[field])
        subject.save()
        return Response(SubjectSerializer(subject).data)

    # DELETE: soft-archive
    subject.is_archived = True
    subject.save(update_fields=['is_archived', 'updated_at'])
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def upload_subject_photos(request, subject_uuid):
    """
    Accept one or more files under the `photos` field. Each becomes an Asset
    + a SubjectPhoto join row. After the upload completes, enqueue the
    auto-describe job.
    """
    org = get_user_org(request.user)
    subject = get_object_or_404(Subject, uuid=subject_uuid, organization=org)

    files = request.FILES.getlist('photos')
    if not files:
        return Response({'error': 'No photos provided (use field name "photos")'},
                        status=status.HTTP_400_BAD_REQUEST)

    if len(files) > 20:
        return Response({'error': 'Max 20 photos per upload'},
                        status=status.HTTP_400_BAD_REQUEST)

    existing_count = subject.subject_photos.count()
    created = []
    for i, f in enumerate(files):
        try:
            asset = ingest_user_upload(
                organization=org, user=request.user,
                uploaded_file=f, kind=AssetKind.SUBJECT_PHOTO,
            )
            sp = SubjectPhoto.objects.create(
                subject=subject,
                asset=asset,
                order=existing_count + i,
                is_primary=(existing_count == 0 and i == 0),  # first ever photo is primary
            )
            created.append(sp)
        except Exception as e:
            logger.error(f'upload_subject_photos: failed for file {f.name}: {e}')

    # Re-describe after photo changes
    run_job('default', jobs.auto_describe_subject, subject.id)

    return Response(SubjectSerializer(subject).data, status=status.HTTP_201_CREATED)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_subject_photo(request, subject_uuid, photo_id):
    org = get_user_org(request.user)
    subject = get_object_or_404(Subject, uuid=subject_uuid, organization=org)
    photo = get_object_or_404(SubjectPhoto, id=photo_id, subject=subject)
    photo.delete()
    # Re-describe after change
    run_job('default', jobs.auto_describe_subject, subject.id)
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def set_primary_photo(request, subject_uuid, photo_id):
    org = get_user_org(request.user)
    subject = get_object_or_404(Subject, uuid=subject_uuid, organization=org)
    SubjectPhoto.objects.filter(subject=subject, is_primary=True).update(is_primary=False)
    photo = get_object_or_404(SubjectPhoto, id=photo_id, subject=subject)
    photo.is_primary = True
    photo.save(update_fields=['is_primary', 'updated_at'])
    return Response(SubjectSerializer(subject).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def regenerate_description(request, subject_uuid):
    """Manually trigger the auto-describe job for an existing subject."""
    org = get_user_org(request.user)
    subject = get_object_or_404(Subject, uuid=subject_uuid, organization=org)
    run_job('default', jobs.auto_describe_subject, subject.id)
    return Response({'message': 'Description regeneration enqueued'})
