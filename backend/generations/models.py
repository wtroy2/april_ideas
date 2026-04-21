"""
Generation models — represent a request to produce one or more videos.

Two layers:
  - GenerationBatch: a single user action ("Generate 5 videos of Whiskers
    using the Cooking theme"). Carries shared config + status rollup.
  - Generation: one video within the batch. Has its own status, scenario,
    prompt, output Asset, caption.

The pipeline is RQ-driven (queue=low). Each Generation runs as one job.
"""

import uuid
from django.db import models
from django.conf import settings

from core.models import TimestampedModel


class GenerationStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    RUNNING = 'running', 'Running'
    SUCCEEDED = 'succeeded', 'Succeeded'
    FAILED = 'failed', 'Failed'
    CANCELLED = 'cancelled', 'Cancelled'


class VideoProvider(models.TextChoices):
    """
    Cheapest → most expensive → highest quality. The mapping from these codes
    to actual model IDs lives in providers/__init__.py:get_video_provider().
    """
    # Veo 3.1 family (newest)
    VEO_31_LITE = 'veo_31_lite', 'Veo 3.1 Lite (cheapest, fastest)'
    VEO_31_FAST = 'veo_31_fast', 'Veo 3.1 Fast (balanced)'
    VEO_31      = 'veo_31',      'Veo 3.1 Standard (best quality)'

    # Veo 3.0 family (older but stable)
    VEO_30_FAST = 'veo_30_fast', 'Veo 3.0 Fast'
    VEO_30      = 'veo_30',      'Veo 3.0 Standard'

    # Runway
    RUNWAY_GEN3    = 'runway_gen3',    'Runway Gen-3 Alpha Turbo (cheap legacy, image-to-video)'
    RUNWAY_GEN4    = 'runway_gen4',    'Runway Gen-4 Turbo (fastest image-to-video)'
    RUNWAY_GEN4_5  = 'runway_gen4_5',  'Runway Gen-4.5 (state-of-the-art, text+image to video)'

    # Kling
    KLING_21    = 'kling_21',    'Kling 2.1 Master (cinematic, premium)'

    # Legacy alias for the old hardcoded "runway" → maps to Gen-4 in the factory
    RUNWAY      = 'runway',      '(legacy) Runway'


class GenerationBatch(TimestampedModel):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    organization = models.ForeignKey(
        'orgs.Organization', on_delete=models.CASCADE, related_name='generation_batches'
    )
    created_by = models.ForeignKey(
        'users.CustomUser', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='generation_batches',
    )
    subject = models.ForeignKey(
        'subjects.Subject', on_delete=models.PROTECT, related_name='generation_batches'
    )
    theme = models.ForeignKey(
        'themes.Theme', on_delete=models.PROTECT, related_name='generation_batches'
    )

    # Defaults applied to each child Generation
    provider = models.CharField(max_length=20, choices=VideoProvider.choices, default=VideoProvider.VEO_31_LITE)
    aspect_ratio = models.CharField(max_length=8, default='9:16')
    duration_seconds = models.IntegerField(default=8)

    # Optional user direction applied to every generation in the batch
    extra_detail = models.TextField(blank=True)
    expand_prompts_with_claude = models.BooleanField(default=True)
    generate_captions = models.BooleanField(default=True)

    # How many independent takes (different seeds) per scenario. 3 scenarios
    # with variations_per_scenario=4 → 12 Generation rows total, grouped by
    # scenario in the batch detail UI.
    variations_per_scenario = models.IntegerField(default=1)

    # When True (default): pass the subject's primary photo to Veo as the
    # first frame of every video — character looks exactly like the photo,
    # but the photo's background carries through.
    # When False: skip passing the photo entirely. Veo does text-to-video
    # using the auto-description. Background is freshly generated per scenario,
    # but pet appearance may drift more.
    use_photo_background = models.BooleanField(default=True)

    # People-in-videos policy. The pipeline keeps Veo's safety setting and the
    # prompt-text instruction symmetric — picking "no people" both tells Veo
    # to refuse human generation AND prepends the prompt with "no people, no
    # humans". Picking "allow" relaxes both sides so Veo can naturally include
    # a human (dog walker, person in the scene) when the prompt implies one.
    # This avoids the trap where the prompt implies a person but the safety
    # setting blocks it.
    PERSON_GENERATION_CHOICES = [
        ('allow_adult', 'Allow people (recommended) — Veo decides if any are needed; no minors'),
        ('dont_allow',  'No people in videos — both Veo + prompt enforce'),
        ('allow_all',   'Allow everyone, including kids (rare)'),
        # 'auto' kept as a legacy value for pre-existing rows; treated as
        # allow_adult by the pipeline. No longer offered in the UI.
        ('auto',        '(legacy) Auto'),
    ]
    person_generation = models.CharField(
        max_length=20, choices=PERSON_GENERATION_CHOICES, default='allow_adult',
    )

    # ---------------- Audio mix (applied to every video in the batch) ----------------
    # Veo's native (scene) audio
    original_audio_volume = models.FloatField(default=0.7)             # 0.0=mute → 1.0=full
    original_audio_fade_in_seconds = models.FloatField(default=0.0)
    original_audio_fade_out_seconds = models.FloatField(default=0.5)

    # Optional user-uploaded music track
    music_track = models.ForeignKey(
        'assets.Asset', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='used_as_music_in_batches',
        limit_choices_to={'kind': 'audio'},
    )
    music_volume = models.FloatField(default=0.5)                       # 0.0=mute → 1.0=full
    music_start_offset_seconds = models.FloatField(default=0.0)         # where in the track to begin
    music_fade_in_seconds = models.FloatField(default=0.5)
    music_fade_out_seconds = models.FloatField(default=1.0)

    status = models.CharField(max_length=20, choices=GenerationStatus.choices, default=GenerationStatus.PENDING)
    notes = models.TextField(blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['organization', 'status']),
            models.Index(fields=['subject', 'status']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f'Batch {self.uuid} ({self.subject.name} / {self.theme.name})'

    def recompute_status(self):
        """Update the batch status based on its children."""
        children = self.generations.all()
        if not children.exists():
            return
        statuses = set(children.values_list('status', flat=True))
        if statuses == {GenerationStatus.SUCCEEDED}:
            self.status = GenerationStatus.SUCCEEDED
        elif statuses <= {GenerationStatus.SUCCEEDED, GenerationStatus.FAILED, GenerationStatus.CANCELLED}:
            # All terminal — mark succeeded if any succeeded, else failed
            self.status = GenerationStatus.SUCCEEDED if GenerationStatus.SUCCEEDED in statuses else GenerationStatus.FAILED
        elif GenerationStatus.RUNNING in statuses or GenerationStatus.PENDING in statuses:
            self.status = GenerationStatus.RUNNING
        self.save(update_fields=['status', 'updated_at'])


class Generation(TimestampedModel):
    """A single video. Produced either for a flat Batch (one-off generations)
    or for a Story Scene (one take in a multi-scene long-form video).
    Exactly one of `batch` or `scene` is set."""

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    batch = models.ForeignKey(
        GenerationBatch, on_delete=models.CASCADE, related_name='generations',
        null=True, blank=True,
    )
    scene = models.ForeignKey(
        'stories.StoryScene', on_delete=models.CASCADE, related_name='generations',
        null=True, blank=True,
    )

    scenario = models.CharField(
        max_length=500, blank=True,
        help_text='Per-video twist (e.g. "tiny pancakes", "the vacuum cleaner")',
    )
    # Which take within the scenario this is (0-indexed). Used for UI grouping
    # ("Take 1", "Take 2", …) and so the seed can vary per take.
    take_index = models.IntegerField(default=0)
    detail = models.TextField(blank=True)

    # The actual prompt sent to the provider (after template render + optional Claude expansion)
    rendered_prompt = models.TextField(blank=True)

    # Output
    # video_asset is the FINAL mixed video shown to users (post-audio-mix).
    # video_asset_raw is what Veo returned, before the music + volume mix applied.
    # When no music is set and audio mix is identity, both point to the same row.
    video_asset = models.ForeignKey(
        'assets.Asset', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='generation_outputs',
    )
    video_asset_raw = models.ForeignKey(
        'assets.Asset', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='generation_raw_outputs',
    )
    caption = models.TextField(blank=True)

    status = models.CharField(max_length=20, choices=GenerationStatus.choices, default=GenerationStatus.PENDING)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    rq_job_id = models.CharField(max_length=64, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['batch', 'status']),
            models.Index(fields=['status', 'created_at']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f'Generation {self.uuid} ({self.get_status_display()})'

    def duration_ms(self):
        if self.started_at and self.finished_at:
            return int((self.finished_at - self.started_at).total_seconds() * 1000)
        return None


class AudioMix(TimestampedModel):
    """
    A baked audio mix for a Generation. Multiple mixes can be saved per
    generation — the user can iterate on settings and compare versions,
    and we never destructively overwrite the Veo-native audio.

    Lifecycle:
      - User tweaks batch-level settings + clicks "Save mix"
      - We create one AudioMix per Generation in the batch (status=pending)
      - remix_generation() runs ffmpeg, sets output_asset, status=ready
      - Generation.video_asset is updated to the new mix's output_asset
      - Raw Veo output always stays in video_asset_raw (never touched)
    """

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    generation = models.ForeignKey(
        'generations.Generation', on_delete=models.CASCADE, related_name='mixes',
    )

    # Dup'd settings at time of bake (immutable snapshot)
    original_audio_volume = models.FloatField(default=1.0)
    original_audio_fade_in_seconds = models.FloatField(default=0.0)
    original_audio_fade_out_seconds = models.FloatField(default=0.0)

    music_track = models.ForeignKey(
        'assets.Asset', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='used_in_mixes',
        limit_choices_to={'kind': 'audio'},
    )
    music_volume = models.FloatField(default=0.5)
    music_start_offset_seconds = models.FloatField(default=0.0)
    music_fade_in_seconds = models.FloatField(default=0.0)
    music_fade_out_seconds = models.FloatField(default=0.0)

    output_asset = models.ForeignKey(
        'assets.Asset', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='as_audio_mix_output',
    )

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('ready', 'Ready'),
        ('failed', 'Failed'),
    ]
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    error_message = models.TextField(blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['generation', '-created_at']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f'AudioMix for {self.generation.uuid} ({self.status})'

    def is_passthrough(self):
        """Would applying this mix change the video at all?"""
        return (
            self.music_track_id is None
            and self.original_audio_volume == 1.0
            and self.original_audio_fade_in_seconds == 0.0
            and self.original_audio_fade_out_seconds == 0.0
        )
