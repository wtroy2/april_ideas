"""Shared model mixins for Critter."""

from django.db import models


class TimestampedModel(models.Model):
    """Adds created_at + updated_at to any model."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class OrgScopedModel(TimestampedModel):
    """
    Marker abstract base for models that belong to a specific Organization.

    Subclasses must add `organization = models.ForeignKey('orgs.Organization', ...)`.
    Kept as a marker rather than declaring the FK here so each subclass can
    customize related_name and on_delete behavior.
    """

    class Meta:
        abstract = True
