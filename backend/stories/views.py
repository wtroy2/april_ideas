"""Story views — CRUD + plan + generate + pick + stitch."""

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
from generations.models import Generation, GenerationStatus

from .models import StoryProject, StoryScene, StoryStatus
from .serializers import StoryProjectSerializer, StorySceneSerializer, CreateStorySerializer
from . import jobs

logger = logging.getLogger('stories')


# ---------------------------------------------------------------------------
# Story CRUD
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_stories(request):
    org = get_user_org(request.user)
    if not org:
        return Response([])
    qs = StoryProject.objects.filter(organization=org).select_related('subject', 'theme')
    return Response(StoryProjectSerializer(qs[:100], many=True).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def story_detail(request, story_uuid):
    org = get_user_org(request.user)
    project = get_object_or_404(
        StoryProject.objects.prefetch_related('scenes__generations__video_asset'),
        uuid=story_uuid, organization=org,
    )
    return Response(StoryProjectSerializer(project).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_story(request):
    org = get_user_org(request.user)
    if not org:
        return Response({'error': 'You must belong to an organization'},
                        status=status.HTTP_400_BAD_REQUEST)

    s = CreateStorySerializer(data=request.data)
    if not s.is_valid():
        return Response(s.errors, status=status.HTTP_400_BAD_REQUEST)
    data = s.validated_data

    subject = get_object_or_404(Subject, uuid=data['subject_uuid'], organization=org, is_archived=False)
    theme = None
    if data.get('theme_uuid'):
        theme = get_object_or_404(Theme, uuid=data['theme_uuid'])
        if theme.organization and theme.organization != org:
            return Response({'error': 'Theme not accessible'}, status=status.HTTP_403_FORBIDDEN)

    if subject.subject_photos.count() == 0:
        return Response({'error': 'Subject needs at least one photo'}, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        project = StoryProject.objects.create(
            organization=org,
            created_by=request.user,
            subject=subject, theme=theme,
            title=data.get('title', ''),
            concept=data['concept'],
            provider=data['provider'],
            aspect_ratio=data['aspect_ratio'],
            target_duration_seconds=data['target_duration_seconds'],
            per_scene_duration_seconds=data['per_scene_duration_seconds'],
            extra_detail=data.get('extra_detail', ''),
            expand_prompts_with_claude=data['expand_prompts_with_claude'],
            use_photo_background=data['use_photo_background'],
            person_generation=data['person_generation'],
            status=StoryStatus.DRAFT,
        )

    # Kick off Claude planning in the background
    run_job('default', jobs.plan_story, project.id)
    return Response(StoryProjectSerializer(project).data, status=status.HTTP_201_CREATED)


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def update_story(request, story_uuid):
    """Edit high-level fields — title, concept, audio mix, music, person_generation, etc.
    Does NOT auto-replan on concept change — call /replan/ explicitly."""
    org = get_user_org(request.user)
    project = get_object_or_404(StoryProject, uuid=story_uuid, organization=org)

    editable = [
        'title', 'concept', 'provider', 'aspect_ratio',
        'target_duration_seconds', 'per_scene_duration_seconds',
        'extra_detail', 'expand_prompts_with_claude', 'generate_captions',
        'use_photo_background', 'person_generation',
        'original_audio_volume', 'original_audio_fade_in_seconds', 'original_audio_fade_out_seconds',
        'music_volume', 'music_start_offset_seconds',
        'music_fade_in_seconds', 'music_fade_out_seconds',
    ]
    for f in editable:
        if f in request.data:
            setattr(project, f, request.data[f])

    # Music track comes by uuid
    if 'music_track_uuid' in request.data:
        track_uuid = request.data['music_track_uuid']
        if not track_uuid:
            project.music_track = None
        else:
            from assets.models import Asset, AssetKind
            try:
                project.music_track = Asset.objects.get(
                    uuid=track_uuid, organization=org, kind=AssetKind.AUDIO,
                )
            except Asset.DoesNotExist:
                return Response({'error': 'music_track_uuid not found'}, status=status.HTTP_400_BAD_REQUEST)

    project.save()
    return Response(StoryProjectSerializer(project).data)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_story(request, story_uuid):
    org = get_user_org(request.user)
    project = get_object_or_404(StoryProject, uuid=story_uuid, organization=org)
    project.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def replan_story(request, story_uuid):
    """Re-run the Claude planner (e.g. after the user edits the concept)."""
    org = get_user_org(request.user)
    project = get_object_or_404(StoryProject, uuid=story_uuid, organization=org)
    run_job('default', jobs.plan_story, project.id)
    project.status = StoryStatus.PLANNING
    project.save(update_fields=['status', 'updated_at'])
    return Response(StoryProjectSerializer(project).data)


# ---------------------------------------------------------------------------
# Scene editing
# ---------------------------------------------------------------------------

@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def update_scene(request, story_uuid, scene_id):
    org = get_user_org(request.user)
    project = get_object_or_404(StoryProject, uuid=story_uuid, organization=org)
    scene = get_object_or_404(StoryScene, id=scene_id, project=project)

    for f in ('title', 'prompt', 'duration_seconds', 'desired_takes', 'transition_out', 'order'):
        if f in request.data:
            setattr(scene, f, request.data[f])
    scene.save()
    return Response(StorySceneSerializer(scene).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_scene(request, story_uuid):
    """Insert a new scene at a given order; pushes later scenes down."""
    org = get_user_org(request.user)
    project = get_object_or_404(StoryProject, uuid=story_uuid, organization=org)

    order = int(request.data.get('order', project.scenes.count()))
    title = request.data.get('title', f'Scene {order + 1}')
    prompt = request.data.get('prompt', '')
    duration = int(request.data.get('duration_seconds', project.per_scene_duration_seconds))
    if duration not in (4, 6, 8):
        duration = project.per_scene_duration_seconds

    with transaction.atomic():
        # Shift later scenes' order up by 1
        project.scenes.filter(order__gte=order).update(order=models.F('order') + 1)
        scene = StoryScene.objects.create(
            project=project, order=order,
            title=title, prompt=prompt, duration_seconds=duration,
        )
    return Response(StorySceneSerializer(scene).data, status=status.HTTP_201_CREATED)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_scene(request, story_uuid, scene_id):
    org = get_user_org(request.user)
    project = get_object_or_404(StoryProject, uuid=story_uuid, organization=org)
    scene = get_object_or_404(StoryScene, id=scene_id, project=project)
    with transaction.atomic():
        order = scene.order
        scene.delete()
        # Close the gap
        project.scenes.filter(order__gt=order).update(order=models.F('order') - 1)
    return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_scene(request, story_uuid, scene_id):
    """Kick off N takes for a single scene (N = scene.desired_takes)."""
    org = get_user_org(request.user)
    project = get_object_or_404(StoryProject, uuid=story_uuid, organization=org)
    scene = get_object_or_404(StoryScene, id=scene_id, project=project)

    if not scene.prompt.strip():
        return Response({'error': 'Scene has no prompt'}, status=status.HTTP_400_BAD_REQUEST)

    run_job('low', jobs.generate_scene, scene.id)
    return Response(StorySceneSerializer(scene).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_all_scenes(request, story_uuid):
    """Kick off all scenes' takes in parallel."""
    org = get_user_org(request.user)
    project = get_object_or_404(StoryProject, uuid=story_uuid, organization=org)
    if not project.scenes.exists():
        return Response({'error': 'No scenes to generate'}, status=status.HTTP_400_BAD_REQUEST)

    for scene in project.scenes.all():
        if scene.prompt.strip():
            run_job('low', jobs.generate_scene, scene.id)
    project.status = StoryStatus.GENERATING
    project.save(update_fields=['status', 'updated_at'])
    return Response(StoryProjectSerializer(project).data)


# ---------------------------------------------------------------------------
# Picking takes + stitching
# ---------------------------------------------------------------------------

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def pick_take(request, story_uuid, scene_id, generation_uuid):
    org = get_user_org(request.user)
    project = get_object_or_404(StoryProject, uuid=story_uuid, organization=org)
    scene = get_object_or_404(StoryScene, id=scene_id, project=project)
    gen = get_object_or_404(Generation, uuid=generation_uuid, scene=scene)
    if gen.status != GenerationStatus.SUCCEEDED:
        return Response({'error': 'Take must be succeeded to pick'}, status=status.HTTP_400_BAD_REQUEST)
    scene.chosen_generation = gen
    scene.save(update_fields=['chosen_generation', 'updated_at'])
    return Response(StorySceneSerializer(scene).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def stitch_story_view(request, story_uuid):
    org = get_user_org(request.user)
    project = get_object_or_404(StoryProject, uuid=story_uuid, organization=org)

    missing = [s for s in project.scenes.all() if not s.chosen_generation_id]
    if missing:
        return Response({
            'error': f'{len(missing)} scene(s) have no chosen take — pick one per scene first',
            'missing_scene_orders': [s.order for s in missing],
        }, status=status.HTTP_400_BAD_REQUEST)

    run_job('low', jobs.stitch_story, project.id)
    project.status = StoryStatus.STITCHING
    project.save(update_fields=['status', 'updated_at'])
    return Response(StoryProjectSerializer(project).data)


# Needed for add_scene / delete_scene above
from django.db import models  # noqa: E402
