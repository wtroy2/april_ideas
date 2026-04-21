"""
Subject — a saved pet (or person) with reference photos and an auto-generated
description. Re-used across many video generations to keep the character
consistent.
"""

import uuid
from django.db import models

from core.models import TimestampedModel


class SubjectKind(models.TextChoices):
    PET = 'pet', 'Pet'
    PERSON = 'person', 'Person'
    OBJECT = 'object', 'Object'


class SubjectSpecies(models.TextChoices):
    """Optional species hint to improve auto-description prompts."""
    CAT = 'cat', 'Cat'
    DOG = 'dog', 'Dog'
    BIRD = 'bird', 'Bird'
    RABBIT = 'rabbit', 'Rabbit'
    HAMSTER = 'hamster', 'Hamster'
    REPTILE = 'reptile', 'Reptile'
    OTHER = 'other', 'Other'


class Subject(TimestampedModel):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    organization = models.ForeignKey(
        'orgs.Organization', on_delete=models.CASCADE, related_name='subjects'
    )
    created_by = models.ForeignKey(
        'users.CustomUser', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_subjects',
    )

    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=10, choices=SubjectKind.choices, default=SubjectKind.PET)
    species = models.CharField(max_length=20, choices=SubjectSpecies.choices, blank=True)

    # AI-generated visual description used in video gen prompts (e.g. "orange tabby
    # cat with white chest patch, green eyes, slightly fluffy"). Populated by
    # the auto-describe job after the first batch of photos is uploaded.
    auto_description = models.TextField(blank=True)
    user_description = models.TextField(blank=True, help_text='Optional override / addendum')

    is_archived = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=['organization', 'is_archived']),
            models.Index(fields=['organization', 'kind']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} ({self.get_kind_display()})'

    @property
    def description(self):
        """User description takes precedence; otherwise fall back to auto."""
        return self.user_description or self.auto_description

    def reference_photos(self):
        """Return the photo Assets attached to this subject (in order added)."""
        return [sp.asset for sp in self.subject_photos.select_related('asset').all()]


class SubjectPhoto(TimestampedModel):
    """
    Join model attaching photo Assets to a Subject.
    The order field controls which photos are sent first to the video model.
    """
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='subject_photos')
    asset = models.ForeignKey('assets.Asset', on_delete=models.CASCADE, related_name='subject_photo_links')
    order = models.IntegerField(default=0)
    is_primary = models.BooleanField(
        default=False,
        help_text='The "best" reference photo — used as the canonical character image',
    )

    class Meta:
        indexes = [
            models.Index(fields=['subject', 'order']),
        ]
        ordering = ['order', 'created_at']
        unique_together = [('subject', 'asset')]

    def __str__(self):
        return f'Photo {self.order} for {self.subject.name}'
