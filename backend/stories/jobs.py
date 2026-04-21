"""
RQ / inline jobs for stories.

  - plan_story(project_id)   — calls Claude to generate the scene breakdown
  - generate_scene(scene_id) — creates N Generation rows for a scene + runs them
  - stitch_story(project_id) — ffmpeg concat the chosen Generation from each scene,
                               then apply the project-level audio mix
"""

import logging

from django.utils import timezone
from django_rq import job

from .models import StoryProject, StoryScene, StoryStatus

logger = logging.getLogger('stories')


@job('default', timeout=300)
def plan_story(project_id):
    """Generate scene plan via Claude and create StoryScene rows."""
    try:
        project = StoryProject.objects.select_related('subject', 'theme').get(id=project_id)
    except StoryProject.DoesNotExist:
        logger.warning(f'plan_story: project {project_id} not found')
        return

    project.status = StoryStatus.PLANNING
    project.save(update_fields=['status', 'updated_at'])

    try:
        from .planner import plan_scenes
        scenes = plan_scenes(project)
        # Wipe any existing scenes on replan
        project.scenes.all().delete()
        for i, s in enumerate(scenes):
            StoryScene.objects.create(
                project=project,
                order=i,
                title=s['title'],
                prompt=s['prompt'],
                duration_seconds=s['duration_seconds'],
                desired_takes=1,
            )
        project.status = StoryStatus.PLANNED
        project.error_message = ''
        project.save(update_fields=['status', 'error_message', 'updated_at'])
        logger.info(f'Planned story {project.uuid} with {len(scenes)} scenes')
    except Exception as e:
        logger.exception(f'plan_story failed for {project.uuid}: {e}')
        project.status = StoryStatus.FAILED
        project.error_message = str(e)[:2000]
        project.save(update_fields=['status', 'error_message', 'updated_at'])


@job('low', timeout=7200)
def generate_scene(scene_id):
    """
    Produce `desired_takes` Generation rows for this scene. Each take runs the
    standard video pipeline (reusing generations.jobs.run_generation), but
    attached to the scene rather than a batch.
    """
    from generations.models import Generation, GenerationStatus
    from generations.jobs import run_generation

    try:
        scene = StoryScene.objects.select_related('project__subject', 'project__theme').get(id=scene_id)
    except StoryScene.DoesNotExist:
        logger.warning(f'generate_scene: scene {scene_id} not found')
        return

    project = scene.project
    project.status = StoryStatus.GENERATING
    project.save(update_fields=['status', 'updated_at'])

    # Create the Generation rows first (so the user sees them pending in the UI)
    takes = [
        Generation(
            scene=scene,
            scenario=scene.title,   # the scene title doubles as the "scenario" label
            detail='',
            status=GenerationStatus.PENDING,
        )
        for _ in range(max(1, scene.desired_takes))
    ]
    Generation.objects.bulk_create(takes)
    gen_ids = list(scene.generations.filter(status=GenerationStatus.PENDING).values_list('id', flat=True))

    # Run each take synchronously inside this job. Could parallelize later.
    for gen_id in gen_ids:
        try:
            run_generation(gen_id)
        except Exception as e:
            logger.exception(f'run_generation failed for take {gen_id}: {e}')

    # Recompute project status
    any_pending = any(
        s.generations.filter(status__in=[GenerationStatus.PENDING, GenerationStatus.RUNNING]).exists()
        for s in project.scenes.all()
    )
    project.status = StoryStatus.GENERATING if any_pending else StoryStatus.TAKES_READY
    project.save(update_fields=['status', 'updated_at'])


@job('default', timeout=1800)
def stitch_story(project_id):
    """
    Concatenate the chosen Generation of each scene into one long video, apply
    the audio mix, and attach the result as project.final_video_asset.
    """
    try:
        project = StoryProject.objects.prefetch_related('scenes__chosen_generation__video_asset_raw').get(id=project_id)
    except StoryProject.DoesNotExist:
        logger.warning(f'stitch_story: project {project_id} not found')
        return

    project.status = StoryStatus.STITCHING
    project.save(update_fields=['status', 'updated_at'])

    try:
        from assets.storage import get_gcs_client
        from assets.services import register_generated_video
        from .stitcher import stitch_scenes

        ordered_scenes = list(project.scenes.order_by('order'))
        if not ordered_scenes:
            raise RuntimeError('Story has no scenes')

        scene_clips = []
        client = get_gcs_client()
        for scene in ordered_scenes:
            chosen = scene.chosen_generation
            if not chosen:
                raise RuntimeError(
                    f'Scene {scene.order} ({scene.title}) has no chosen take — '
                    f'pick one before stitching'
                )
            # Use the raw Veo output; the audio mix is applied to the final stitched video.
            asset = chosen.video_asset_raw or chosen.video_asset
            if not asset:
                raise RuntimeError(f'Scene {scene.order} chosen take has no video asset')
            video_bytes = client.bucket(asset.bucket).blob(asset.object_key).download_as_bytes()
            scene_clips.append((video_bytes, scene.duration_seconds, scene.transition_out))

        stitched = stitch_scenes(scene_clips=scene_clips)

        # Apply project-level audio mix to the stitched video
        total_duration = sum(s.duration_seconds for s in ordered_scenes)
        final_bytes = _apply_project_audio_mix(stitched, project, total_duration)

        base_filename = f'{project.subject.name.replace(" ", "_")}_{project.uuid}_stitched.mp4'
        final_asset = register_generated_video(
            organization=project.organization,
            video_bytes=final_bytes,
            content_type='video/mp4',
            duration_seconds=total_duration,
            filename=base_filename,
        )
        project.final_video_asset = final_asset
        project.status = StoryStatus.READY
        project.error_message = ''
        project.save(update_fields=['final_video_asset', 'status', 'error_message', 'updated_at'])
        logger.info(f'Stitched story {project.uuid}: {total_duration}s across {len(ordered_scenes)} scenes')

    except Exception as e:
        logger.exception(f'stitch_story failed for {project.uuid}: {e}')
        project.status = StoryStatus.FAILED
        project.error_message = str(e)[:2000]
        project.save(update_fields=['status', 'error_message', 'updated_at'])


def _apply_project_audio_mix(video_bytes, project, total_duration):
    """Apply the project-level audio mix to the stitched video."""
    import os
    import tempfile
    from assets.audio_mix import apply_audio_mix, AudioMixSettings
    from assets.storage import get_gcs_client

    # Fast path: passthrough if nothing to do
    if (project.music_track_id is None
            and project.original_audio_volume == 1.0
            and project.original_audio_fade_in_seconds == 0.0
            and project.original_audio_fade_out_seconds == 0.0):
        return video_bytes

    music_path = None
    music_tmp = None
    if project.music_track_id:
        try:
            ma = project.music_track
            client = get_gcs_client()
            mb = client.bucket(ma.bucket).blob(ma.object_key).download_as_bytes()
            music_tmp = tempfile.NamedTemporaryFile(suffix='.audio', delete=False)
            music_tmp.write(mb)
            music_tmp.close()
            music_path = music_tmp.name
        except Exception as e:
            logger.warning(f'Could not download music for story {project.uuid}: {e}')

    settings = AudioMixSettings(
        duration_seconds=total_duration,
        original_volume=project.original_audio_volume,
        original_fade_in_seconds=project.original_audio_fade_in_seconds,
        original_fade_out_seconds=project.original_audio_fade_out_seconds,
        music_path=music_path,
        music_start_offset_seconds=project.music_start_offset_seconds,
        music_volume=project.music_volume,
        music_fade_in_seconds=project.music_fade_in_seconds,
        music_fade_out_seconds=project.music_fade_out_seconds,
    )
    try:
        return apply_audio_mix(video_bytes, settings)
    finally:
        if music_tmp:
            try:
                os.unlink(music_tmp.name)
            except OSError:
                pass
