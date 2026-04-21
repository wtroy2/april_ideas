"""
Theme — a reusable template that defines the *style* of a generation:
shot structure, mood/vibe, music feel, caption style, and a prompt template
that the generation pipeline interpolates with the Subject's description and
any per-generation user input.

Two flavors:
  - System themes (organization=null) — seeded curated templates we ship
    with the product (cat ASMR cooking, dog day-in-the-life, etc.)
  - Org themes (organization=<org>) — custom templates the org has built or
    forked from a system theme.
"""

import uuid
from django.db import models

from core.models import TimestampedModel


class ShotStyle(models.TextChoices):
    CINEMATIC = 'cinematic', 'Cinematic'
    HANDHELD = 'handheld', 'Handheld / iPhone'
    MACRO = 'macro', 'Macro / close-up'
    OVERHEAD = 'overhead', 'Overhead'
    POV = 'pov', 'POV'
    STUDIO = 'studio', 'Studio'


class MusicVibe(models.TextChoices):
    ASMR_AMBIENT = 'asmr_ambient', 'ASMR / ambient'
    LOFI = 'lofi', 'Lo-fi'
    UPBEAT = 'upbeat', 'Upbeat'
    EMOTIONAL = 'emotional', 'Emotional / cinematic'
    TRENDING = 'trending', 'Trending audio (substitute later)'
    SILENT = 'silent', 'Silent / dialogue only'


class Theme(TimestampedModel):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)

    # null = system theme available to all orgs
    organization = models.ForeignKey(
        'orgs.Organization', on_delete=models.CASCADE,
        related_name='themes', null=True, blank=True,
    )

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=120)
    description = models.TextField(blank=True)
    cover_emoji = models.CharField(max_length=8, blank=True)  # quick visual in the UI

    # Style
    shot_style = models.CharField(max_length=20, choices=ShotStyle.choices, default=ShotStyle.HANDHELD)
    music_vibe = models.CharField(max_length=20, choices=MusicVibe.choices, default=MusicVibe.LOFI)

    # Prompt template — supports {subject_description}, {subject_name},
    # {scenario}, {detail} placeholders. Engine fills these in before sending
    # to the video provider.
    prompt_template = models.TextField(
        help_text='Template with {subject_description}, {subject_name}, {scenario}, {detail} placeholders'
    )

    # Caption template — same placeholder system, sent to Anthropic for
    # final caption polishing.
    caption_template = models.TextField(blank=True)

    # Default scenario seeds (one per video in a batch). Examples for a
    # "Cat reacts" theme: ["the vacuum cleaner", "a cucumber", "a bath"].
    default_scenarios = models.JSONField(default=list, blank=True)

    # Tags for browsing
    tags = models.JSONField(default=list, blank=True)

    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=['organization', 'is_active']),
            models.Index(fields=['is_featured', 'is_active']),
        ]
        unique_together = [('organization', 'slug')]
        ordering = ['-is_featured', 'name']

    def __str__(self):
        scope = self.organization.name if self.organization else 'system'
        return f'{self.name} ({scope})'

    @property
    def is_system(self):
        return self.organization_id is None

    def render_prompt(self, *, subject, scenario='', detail=''):
        """Fill in the prompt template for a given subject + scenario."""
        return self.prompt_template.format(
            subject_description=subject.description or 'the subject',
            subject_name=subject.name,
            scenario=scenario or '',
            detail=detail or '',
        )

    def render_caption_prompt(self, *, subject, scenario='', detail=''):
        """Fill in the caption template (sent to Anthropic for polish)."""
        if not self.caption_template:
            return ''
        return self.caption_template.format(
            subject_description=subject.description or 'the subject',
            subject_name=subject.name,
            scenario=scenario or '',
            detail=detail or '',
        )
