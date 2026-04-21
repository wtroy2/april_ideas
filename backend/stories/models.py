"""
Long-form stories — multi-scene videos stitched together from individual AI
clips. Each StoryProject has an ordered list of StoryScenes; each scene can
have N takes (Generation rows) and the user picks their favorite per scene.
"""

import uuid
from django.db import models

from core.models import TimestampedModel


class StoryStatus(models.TextChoices):
    DRAFT = 'draft', 'Draft'                     # just created, no plan yet
    PLANNING = 'planning', 'Planning scenes…'    # Claude generating the scene breakdown
    PLANNED = 'planned', 'Planned, not generated'  # user is reviewing/editing the plan
    GENERATING = 'generating', 'Generating takes…'
    TAKES_READY = 'takes_ready', 'Takes ready, waiting for picks'
    STITCHING = 'stitching', 'Stitching final video…'
    READY = 'ready', 'Ready'
    FAILED = 'failed', 'Failed'


class StoryProject(TimestampedModel):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    organization = models.ForeignKey('orgs.Organization', on_delete=models.CASCADE, related_name='stories')
    created_by = models.ForeignKey(
        'users.CustomUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='stories',
    )
    subject = models.ForeignKey('subjects.Subject', on_delete=models.PROTECT, related_name='stories')
    # Theme is optional — used as a global style hint for the scene plan
    theme = models.ForeignKey('themes.Theme', on_delete=models.SET_NULL, null=True, blank=True, related_name='stories')

    title = models.CharField(max_length=200, blank=True)
    concept = models.TextField(
        help_text='The one-line pitch Claude uses to plan the scenes. '
                  'E.g. "Mr Kitty discovers Antarctica and befriends a penguin."',
    )

    # Same shared-config fields as GenerationBatch (applied to every scene)
    provider = models.CharField(max_length=20, default='veo_31_lite')
    aspect_ratio = models.CharField(max_length=8, default='9:16')
    target_duration_seconds = models.IntegerField(default=30, help_text='Total video length target')
    per_scene_duration_seconds = models.IntegerField(default=8, choices=[(4, '4s'), (6, '6s'), (8, '8s')])

    extra_detail = models.TextField(blank=True)
    expand_prompts_with_claude = models.BooleanField(default=True)
    generate_captions = models.BooleanField(default=False)
    use_photo_background = models.BooleanField(default=True)
    person_generation = models.CharField(max_length=20, default='allow_adult')

    # Audio mix (applied to the stitched final video, not per-scene)
    original_audio_volume = models.FloatField(default=0.7)
    original_audio_fade_in_seconds = models.FloatField(default=0.0)
    original_audio_fade_out_seconds = models.FloatField(default=0.5)
    music_track = models.ForeignKey(
        'assets.Asset', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='used_in_stories',
        limit_choices_to={'kind': 'audio'},
    )
    music_volume = models.FloatField(default=0.5)
    music_start_offset_seconds = models.FloatField(default=0.0)
    music_fade_in_seconds = models.FloatField(default=0.5)
    music_fade_out_seconds = models.FloatField(default=1.0)

    # Output of the stitch step
    final_video_asset = models.ForeignKey(
        'assets.Asset', on_delete=models.SET_NULL, null=True, blank=True, related_name='story_finals',
    )

    status = models.CharField(max_length=20, choices=StoryStatus.choices, default=StoryStatus.DRAFT)
    error_message = models.TextField(blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['organization', 'status']),
            models.Index(fields=['subject']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return self.title or f'Story {self.uuid}'


class TransitionKind(models.TextChoices):
    CUT = 'cut', 'Hard cut'
    CROSSFADE = 'crossfade', 'Crossfade (0.5s)'
    FADE_BLACK = 'fade_black', 'Fade through black (0.5s)'


class StoryScene(TimestampedModel):
    """One scene in the story. Can have N takes (Generation rows) and the user picks one."""

    project = models.ForeignKey(StoryProject, on_delete=models.CASCADE, related_name='scenes')
    order = models.IntegerField(default=0)

    title = models.CharField(max_length=200, help_text='Short label, e.g. "Mr Kitty steps off the spaceship"')
    prompt = models.TextField(help_text='The actual Veo prompt for this scene (before auto-describe/Claude expansion)')
    duration_seconds = models.IntegerField(default=8, choices=[(4, '4s'), (6, '6s'), (8, '8s')])

    desired_takes = models.IntegerField(default=1, help_text='How many variations to generate for this scene')
    transition_out = models.CharField(
        max_length=20, choices=TransitionKind.choices, default=TransitionKind.CROSSFADE,
        help_text='Transition TO the next scene (ignored on the last scene)',
    )

    # User's favorite take — set when they click "use this one"
    chosen_generation = models.ForeignKey(
        'generations.Generation', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='chosen_in_scenes',
    )

    class Meta:
        indexes = [
            models.Index(fields=['project', 'order']),
        ]
        ordering = ['order']
        unique_together = [('project', 'order')]

    def __str__(self):
        return f'{self.project.title or self.project.uuid} — scene {self.order}: {self.title}'

    @property
    def takes(self):
        """All Generation rows produced for this scene."""
        return self.generations.all()
