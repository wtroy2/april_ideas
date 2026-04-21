"""Generation views — list, detail, create batch, regenerate single."""

import logging

from django.shortcuts import get_object_or_404
from django.db import transaction

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.jobs import run_job
from orgs.permissions import get_user_org
from subjects.models import Subject
from themes.models import Theme

from .models import GenerationBatch, Generation, GenerationStatus
from .serializers import GenerationBatchSerializer, GenerationSerializer, CreateBatchSerializer
from . import jobs

logger = logging.getLogger('generations')


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_batches(request):
    org = get_user_org(request.user)
    if not org:
        return Response([])
    qs = GenerationBatch.objects.filter(organization=org).select_related('subject', 'theme')
    return Response(GenerationBatchSerializer(qs[:100], many=True).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def batch_detail(request, batch_uuid):
    org = get_user_org(request.user)
    batch = get_object_or_404(
        GenerationBatch.objects.prefetch_related('generations__video_asset'),
        uuid=batch_uuid, organization=org,
    )
    return Response(GenerationBatchSerializer(batch).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_batch(request):
    """
    Create a GenerationBatch + N Generation rows (one per scenario), then
    enqueue each one on the `low` queue for Veo/Runway processing.
    """
    org = get_user_org(request.user)
    if not org:
        return Response({'error': 'You must belong to an organization'},
                        status=status.HTTP_400_BAD_REQUEST)

    serializer = CreateBatchSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data

    subject = get_object_or_404(Subject, uuid=data['subject_uuid'], organization=org, is_archived=False)
    theme = get_object_or_404(Theme, uuid=data['theme_uuid'])
    if theme.organization and theme.organization != org:
        return Response({'error': 'Theme not accessible'}, status=status.HTTP_403_FORBIDDEN)

    if subject.subject_photos.count() == 0:
        return Response({'error': 'Subject needs at least one photo before generation'},
                        status=status.HTTP_400_BAD_REQUEST)

    # Quota check
    from billing.models import OrganizationBilling, PlanTier
    billing, _ = OrganizationBilling.objects.get_or_create(
        organization=org, defaults={'plan': PlanTier.FREE, 'monthly_generation_quota': 10},
    )
    total_gens = len(data['scenarios']) * data['variations_per_scenario']
    if billing.generations_used_this_period + total_gens > billing.monthly_generation_quota:
        return Response({
            'error': 'Quota exceeded',
            'used': billing.generations_used_this_period,
            'quota': billing.monthly_generation_quota,
            'requested': total_gens,
        }, status=status.HTTP_402_PAYMENT_REQUIRED)

    with transaction.atomic():
        batch = GenerationBatch.objects.create(
            organization=org,
            created_by=request.user,
            subject=subject,
            theme=theme,
            provider=data['provider'],
            aspect_ratio=data['aspect_ratio'],
            duration_seconds=data['duration_seconds'],
            extra_detail=data.get('extra_detail', ''),
            expand_prompts_with_claude=data['expand_prompts_with_claude'],
            generate_captions=data['generate_captions'],
            use_photo_background=data['use_photo_background'],
            person_generation=data['person_generation'],
            variations_per_scenario=data['variations_per_scenario'],
            notes=data.get('notes', ''),
            # Audio mix starts at identity defaults (no music, no fade, full
            # original volume). User tunes on the detail page + hits Remix.
            original_audio_volume=1.0,
            music_volume=0.5,
            status=GenerationStatus.PENDING,
        )
        # N scenarios × M takes = N×M Generation rows. Seed per take differs so
        # the same scenario actually produces different videos.
        gens = []
        variations = data['variations_per_scenario']
        for scenario in data['scenarios']:
            for take_idx in range(variations):
                gens.append(Generation(batch=batch, scenario=scenario, take_index=take_idx))
        Generation.objects.bulk_create(gens)
        gen_ids = list(batch.generations.values_list('id', flat=True))

    # Dispatch each generation — either RQ or inline thread, depending on settings.
    for gen_id in gen_ids:
        result = run_job('low', jobs.run_generation, gen_id)
        # If RQ returned a job, capture the id; in inline mode result is a Thread.
        rq_id = getattr(result, 'id', '')
        if rq_id:
            Generation.objects.filter(id=gen_id).update(rq_job_id=rq_id)

    return Response(GenerationBatchSerializer(batch).data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def regenerate(request, generation_uuid):
    """Re-run a single Generation (e.g. user wasn't happy with the result)."""
    org = get_user_org(request.user)
    gen = get_object_or_404(Generation, uuid=generation_uuid, batch__organization=org)

    # Reset state
    gen.status = GenerationStatus.PENDING
    gen.started_at = None
    gen.finished_at = None
    gen.error_message = ''
    gen.video_asset = None
    gen.caption = ''
    gen.rendered_prompt = ''
    gen.save()

    result = run_job('low', jobs.run_generation, gen.id)
    rq_id = getattr(result, 'id', '')
    if rq_id:
        Generation.objects.filter(id=gen.id).update(rq_job_id=rq_id)

    return Response(GenerationSerializer(gen).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cancel_generation(request, generation_uuid):
    org = get_user_org(request.user)
    gen = get_object_or_404(Generation, uuid=generation_uuid, batch__organization=org)
    if gen.status not in (GenerationStatus.PENDING, GenerationStatus.RUNNING):
        return Response({'error': f'Cannot cancel a {gen.get_status_display()} generation'},
                        status=status.HTTP_400_BAD_REQUEST)
    gen.status = GenerationStatus.CANCELLED
    gen.save(update_fields=['status', 'updated_at'])
    return Response(GenerationSerializer(gen).data)


# ---------------------------------------------------------------------------
# Audio mix — post-generation, separate from the video pipeline
# ---------------------------------------------------------------------------

@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def update_batch_audio(request, batch_uuid):
    """
    Save the batch's draft audio mix settings. Does NOT bake an MP4 — UI can
    live-preview the changes in the browser. Call /remix/ when ready to
    produce an actual mixed MP4.
    """
    from .serializers import UpdateBatchAudioSerializer
    org = get_user_org(request.user)
    batch = get_object_or_404(GenerationBatch, uuid=batch_uuid, organization=org)

    s = UpdateBatchAudioSerializer(data=request.data, partial=True)
    if not s.is_valid():
        return Response(s.errors, status=status.HTTP_400_BAD_REQUEST)
    data = s.validated_data

    # Music track resolves by uuid
    if 'music_track_uuid' in data:
        track_uuid = data.pop('music_track_uuid')
        if not track_uuid:
            batch.music_track = None
        else:
            from assets.models import Asset, AssetKind
            try:
                batch.music_track = Asset.objects.get(
                    uuid=track_uuid, organization=org, kind=AssetKind.AUDIO,
                )
            except Asset.DoesNotExist:
                return Response({'error': 'music_track_uuid not found'},
                                status=status.HTTP_400_BAD_REQUEST)

    for field, value in data.items():
        setattr(batch, field, value)
    batch.save()

    return Response(GenerationBatchSerializer(batch).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def remix_batch(request, batch_uuid):
    """Bake the current draft audio settings into every generation in the batch."""
    org = get_user_org(request.user)
    batch = get_object_or_404(GenerationBatch, uuid=batch_uuid, organization=org)
    run_job('default', jobs.remix_batch, batch.id)
    return Response({
        'message': 'Remix queued — generations will update once it finishes',
        'batch_uuid': str(batch.uuid),
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def reset_generation_to_raw(request, generation_uuid):
    """Point Generation.video_asset back at video_asset_raw (undo all mixes)."""
    org = get_user_org(request.user)
    gen = get_object_or_404(
        Generation.objects.filter(batch__organization=org) | Generation.objects.filter(scene__project__organization=org),
        uuid=generation_uuid,
    )
    if not gen.video_asset_raw:
        return Response({'error': 'No raw video to reset to'}, status=status.HTTP_400_BAD_REQUEST)
    gen.video_asset = gen.video_asset_raw
    gen.save(update_fields=['video_asset', 'updated_at'])
    return Response(GenerationSerializer(gen).data)
