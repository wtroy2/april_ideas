"""
RQ jobs for the generation pipeline.

Each Generation runs as a single `run_generation` job on the `low` queue
(timeout 1 hour, since video gen takes 1-5 min per clip and we want headroom).

Flow:
  1. Mark RUNNING
  2. Render prompt from theme template (+ optional Claude expansion)
  3. Pull subject's primary reference photo from GCS
  4. Call the video provider — synchronous from our POV (provider polls internally)
  5. Save generated video as Asset, attach to Generation
  6. Generate caption with Claude (optional)
  7. Mark SUCCEEDED, recompute batch status
  8. Increment org's usage counter (Phase 5 wires Stripe meter)
"""

import logging

from django.utils import timezone
from django_rq import job

from .models import Generation, GenerationStatus, VideoProvider as VP
from assets.services import register_generated_video
from assets.storage import get_gcs_client
from billing.models import OrganizationBilling

logger = logging.getLogger('generations')


@job('low', timeout=3600)
def run_generation(generation_id):
    """
    Produces one video for a Generation row. The Generation is attached to
    either a GenerationBatch (flat one-off generations) OR a StoryScene (one
    take of a multi-scene long-form video). The flow is the same either way;
    we normalize both parents into one `ctx` dict at the top.
    """
    try:
        gen = Generation.objects.select_related(
            'batch__subject', 'batch__theme', 'batch__organization',
            'scene__project__subject', 'scene__project__theme', 'scene__project__organization',
        ).get(id=generation_id)
    except Generation.DoesNotExist:
        logger.warning(f'run_generation: generation {generation_id} not found')
        return

    if gen.status != GenerationStatus.PENDING:
        logger.info(f'Generation {gen.uuid} not pending (status={gen.status}), skipping')
        return

    ctx = _resolve_context(gen)
    subject, theme, org = ctx['subject'], ctx['theme'], ctx['org']

    gen.status = GenerationStatus.RUNNING
    gen.started_at = timezone.now()
    gen.save(update_fields=['status', 'started_at', 'updated_at'])

    try:
        # 1. Build the prompt. Two paths:
        #    - batch mode: theme template + scenario + detail → optional polish
        #    - scene mode: scene.prompt is already a full prompt → optional polish
        # Which LLM runs the polish is controlled by TEXT_POLISH_MODEL in settings
        # (see providers/text.py). Defaults to Gemini Flash.
        if ctx['is_scene']:
            raw_prompt = ctx['raw_prompt']
            if ctx['expand_prompts']:
                from providers.text import polish_prompt
                prompt = polish_prompt(raw_prompt, subject=subject)
            else:
                prompt = raw_prompt
        else:
            if ctx['expand_prompts']:
                from providers.text import expand_prompt
                prompt = expand_prompt(
                    theme=theme, subject=subject,
                    scenario=ctx['scenario'], detail=ctx['detail'],
                )
            else:
                prompt = theme.render_prompt(
                    subject=subject,
                    scenario=ctx['scenario'],
                    detail=ctx['detail'],
                )

        gen.rendered_prompt = prompt
        gen.save(update_fields=['rendered_prompt', 'updated_at'])

        # 2. Reference photo — always pass it if we have one. Passing the image
        # improves character consistency for every provider AND is required by
        # Runway gen3a_turbo / gen4_turbo. The `use_photo_background` toggle
        # DOES NOT drop the image; it just changes the prompt instruction.
        ref_bytes_list = _get_reference_bytes(subject)

        # 2b. If the user wants a fresh background, tell the model explicitly
        # to use the reference only for the subject's appearance, not the scene.
        if not ctx['use_photo_background'] and ref_bytes_list:
            subject_label = _subject_prompt_label(subject)
            prompt = (
                f'IMPORTANT: Use the reference image ONLY to match the appearance '
                f'of the {subject_label}. Do NOT copy the background, setting, or '
                f'environment from the reference image — generate a completely '
                f'fresh scene from the description below. ' + prompt
            )

        # 3. Align Veo's safety knob with the prompt text (see jobs.py history for rationale)
        person_gen = ctx['person_generation']
        if person_gen == 'auto':
            person_gen = 'allow_adult'
        if person_gen == 'dont_allow':
            prompt = (
                'IMPORTANT: no humans, no human faces, no people anywhere in the '
                'scene. Subject is an animal/object only. ' + prompt
            )

        from providers import get_video_provider
        provider = get_video_provider(ctx['provider'])
        result = provider.generate(
            prompt=prompt,
            reference_image_bytes=ref_bytes_list,
            aspect_ratio=ctx['aspect_ratio'],
            duration_seconds=ctx['duration_seconds'],
            person_generation=person_gen,
        )

        # 4. Save raw output
        label = subject.name.replace(' ', '_')
        raw_asset = register_generated_video(
            organization=org,
            video_bytes=result.video_bytes,
            content_type=result.content_type,
            duration_seconds=result.duration_seconds,
            width=result.width, height=result.height,
            filename=f'{label}_{gen.uuid}_raw.mp4',
        )
        gen.video_asset_raw = raw_asset

        # 4b. video_asset starts as the raw Veo output. Audio mixing is a
        # separate, post-generation step (see remix_generation below) — users
        # play with audio settings on the batch detail page and bake a mix
        # when they're happy with the preview.
        gen.video_asset = raw_asset

        # 5. Caption — batch mode only (scenes don't have their own caption)
        if ctx['generate_captions'] and not ctx['is_scene']:
            from providers.text import generate_caption
            try:
                gen.caption = generate_caption(
                    theme=theme, subject=subject,
                    scenario=ctx['scenario'], detail=ctx['detail'],
                )
            except Exception as e:
                logger.warning(f'Caption generation failed for {gen.uuid}: {e}')

        # 6. Mark succeeded
        gen.status = GenerationStatus.SUCCEEDED
        gen.finished_at = timezone.now()
        gen.save()

        # 7. Increment usage
        try:
            billing = OrganizationBilling.objects.filter(organization=org).first()
            if billing:
                billing.increment_usage(1)
        except Exception as e:
            logger.warning(f'Could not increment usage for org {org.id}: {e}')

        logger.info(f'Generation {gen.uuid} succeeded in {gen.duration_ms()}ms')

    except Exception as e:
        logger.error(f'Generation {gen.uuid} failed: {e}', exc_info=True)
        gen.status = GenerationStatus.FAILED
        gen.finished_at = timezone.now()
        gen.error_message = str(e)[:2000]
        gen.save(update_fields=['status', 'finished_at', 'error_message', 'updated_at'])

    finally:
        if gen.batch_id:
            gen.batch.recompute_status()


def _resolve_context(gen):
    """
    Normalize the batch vs scene parent into one config dict used by run_generation.
    """
    if gen.batch_id:
        batch = gen.batch
        return {
            'is_scene': False,
            'subject': batch.subject,
            'theme': batch.theme,
            'org': batch.organization,
            'provider': batch.provider,
            'aspect_ratio': batch.aspect_ratio,
            'duration_seconds': batch.duration_seconds,
            'expand_prompts': batch.expand_prompts_with_claude,
            'generate_captions': batch.generate_captions,
            'use_photo_background': batch.use_photo_background,
            'person_generation': batch.person_generation,
            'scenario': gen.scenario,
            'detail': gen.detail or batch.extra_detail,
            'raw_prompt': None,
        }

    scene = gen.scene
    project = scene.project
    return {
        'is_scene': True,
        'subject': project.subject,
        'theme': project.theme,  # may be None
        'org': project.organization,
        'provider': project.provider,
        'aspect_ratio': project.aspect_ratio,
        'duration_seconds': scene.duration_seconds,
        'expand_prompts': project.expand_prompts_with_claude,
        'generate_captions': False,  # captions only apply to batch mode
        'use_photo_background': project.use_photo_background,
        'person_generation': project.person_generation,
        'scenario': scene.title,
        'detail': '',
        'raw_prompt': scene.prompt,
    }


@job('default', timeout=600)
def remix_generation(mix_id):
    """
    Bake one AudioMix to an MP4 via ffmpeg. On success, updates the mix's
    output_asset and points the parent Generation.video_asset at it.
    """
    import os
    import tempfile
    from django.utils import timezone
    from .models import AudioMix
    from .audio_mix import apply_audio_mix, AudioMixSettings

    try:
        mix = AudioMix.objects.select_related('generation__video_asset_raw', 'music_track').get(id=mix_id)
    except AudioMix.DoesNotExist:
        logger.warning(f'remix_generation: mix {mix_id} not found')
        return

    mix.status = 'running'
    mix.save(update_fields=['status', 'updated_at'])

    try:
        gen = mix.generation
        raw = gen.video_asset_raw
        if not raw:
            raise RuntimeError('Generation has no raw video to remix')

        # Fast path: pure passthrough → just point at raw, don't re-encode
        if mix.is_passthrough():
            mix.output_asset = raw
            mix.status = 'ready'
            mix.save()
            gen.video_asset = raw
            gen.save(update_fields=['video_asset', 'updated_at'])
            logger.info(f'Mix {mix.uuid}: passthrough, no ffmpeg needed')
            return

        # Download the raw video
        client = get_gcs_client()
        raw_bytes = client.bucket(raw.bucket).blob(raw.object_key).download_as_bytes()

        # Optional music track → temp file
        music_path = None
        music_tmp = None
        if mix.music_track_id:
            try:
                mt = mix.music_track
                mb = client.bucket(mt.bucket).blob(mt.object_key).download_as_bytes()
                music_tmp = tempfile.NamedTemporaryFile(suffix='.audio', delete=False)
                music_tmp.write(mb)
                music_tmp.close()
                music_path = music_tmp.name
            except Exception as e:
                logger.warning(f'Mix {mix.uuid}: music download failed, skipping music: {e}')

        try:
            settings_obj = AudioMixSettings(
                duration_seconds=raw.duration_seconds or 8,
                original_volume=mix.original_audio_volume,
                original_fade_in_seconds=mix.original_audio_fade_in_seconds,
                original_fade_out_seconds=mix.original_audio_fade_out_seconds,
                music_path=music_path,
                music_start_offset_seconds=mix.music_start_offset_seconds,
                music_volume=mix.music_volume,
                music_fade_in_seconds=mix.music_fade_in_seconds,
                music_fade_out_seconds=mix.music_fade_out_seconds,
            )
            mixed_bytes = apply_audio_mix(raw_bytes, settings_obj)
        finally:
            if music_tmp:
                try:
                    os.unlink(music_tmp.name)
                except OSError:
                    pass

        # Save as a new asset
        from assets.services import register_generated_video
        subject_label = (gen.batch.subject.name if gen.batch_id else
                         (gen.scene.project.subject.name if gen.scene_id else 'critter'))
        filename = f'{subject_label.replace(" ", "_")}_{gen.uuid}_mix_{mix.uuid.hex[:8]}.mp4'
        out_asset = register_generated_video(
            organization=(gen.batch.organization if gen.batch_id else gen.scene.project.organization),
            video_bytes=mixed_bytes,
            content_type='video/mp4',
            duration_seconds=raw.duration_seconds,
            width=raw.width,
            height=raw.height,
            filename=filename,
        )

        mix.output_asset = out_asset
        mix.status = 'ready'
        mix.error_message = ''
        mix.save()

        # Point the generation at the fresh mix
        gen.video_asset = out_asset
        gen.save(update_fields=['video_asset', 'updated_at'])

        logger.info(f'Baked mix {mix.uuid} for generation {gen.uuid}')

    except Exception as e:
        logger.exception(f'remix_generation failed for mix {mix.id}: {e}')
        mix.status = 'failed'
        mix.error_message = str(e)[:2000]
        mix.save(update_fields=['status', 'error_message', 'updated_at'])


@job('default', timeout=1800)
def remix_batch(batch_id):
    """
    Bake the batch's current audio settings onto every Generation in the batch.
    Creates one AudioMix per generation and kicks each through remix_generation
    synchronously (already on a worker thread; no need to fan out).
    """
    from .models import GenerationBatch, AudioMix

    try:
        batch = GenerationBatch.objects.prefetch_related('generations').get(id=batch_id)
    except GenerationBatch.DoesNotExist:
        logger.warning(f'remix_batch: batch {batch_id} not found')
        return

    gens = list(batch.generations.exclude(video_asset_raw__isnull=True))
    for gen in gens:
        mix = AudioMix.objects.create(
            generation=gen,
            original_audio_volume=batch.original_audio_volume,
            original_audio_fade_in_seconds=batch.original_audio_fade_in_seconds,
            original_audio_fade_out_seconds=batch.original_audio_fade_out_seconds,
            music_track=batch.music_track,
            music_volume=batch.music_volume,
            music_start_offset_seconds=batch.music_start_offset_seconds,
            music_fade_in_seconds=batch.music_fade_in_seconds,
            music_fade_out_seconds=batch.music_fade_out_seconds,
            status='pending',
        )
        remix_generation(mix.id)


def _subject_prompt_label(subject):
    """Human-readable label for the subject, used when telling the model
    'use reference image only to match the appearance of the X'.
    Prefers species for pets ('cat', 'dog'); falls back to kind."""
    if subject.kind == 'pet':
        if subject.species and subject.species != 'other':
            return subject.get_species_display().lower()
        return 'animal'
    if subject.kind == 'person':
        return 'person'
    return 'subject'


def _get_reference_bytes(subject):
    """Pull bytes for the subject's primary photo (or first photo) from GCS."""
    from subjects.models import SubjectPhoto

    primary = (
        SubjectPhoto.objects
        .filter(subject=subject, is_primary=True)
        .select_related('asset')
        .first()
    )
    if not primary:
        primary = (
            SubjectPhoto.objects
            .filter(subject=subject)
            .select_related('asset')
            .order_by('order')
            .first()
        )
    if not primary or not primary.asset:
        return None

    asset = primary.asset
    try:
        client = get_gcs_client()
        return [client.bucket(asset.bucket).blob(asset.object_key).download_as_bytes()]
    except Exception as e:
        logger.warning(f'Could not download reference photo for subject {subject.name}: {e}')
        return None
