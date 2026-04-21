"""
RQ jobs for subjects.

  - auto_describe_subject: Use Gemini Vision to look at the reference photos
    and generate a structured visual description (color, distinguishing
    features, build) that we'll inject into video-gen prompts.
"""

import logging

from django_rq import job

from .models import Subject

logger = logging.getLogger('subjects')


@job('default', timeout=300)
def auto_describe_subject(subject_id):
    """Generate auto_description for a Subject from its reference photos."""
    try:
        subject = Subject.objects.get(id=subject_id)
    except Subject.DoesNotExist:
        logger.warning(f'auto_describe_subject: subject {subject_id} not found')
        return

    photos = subject.reference_photos()
    if not photos:
        logger.info(f'auto_describe_subject: no photos for {subject.name}, skipping')
        return

    # Dispatcher picks backend based on TEXT_DESCRIBE_MODEL (default: gemini_flash).
    from providers.text import describe_subject_from_photos
    try:
        description = describe_subject_from_photos(subject, photos)
        subject.auto_description = description.strip()
        subject.save(update_fields=['auto_description', 'updated_at'])
        logger.info(f'Auto-described subject {subject.name}: {description[:120]}')
    except Exception as e:
        logger.error(f'auto_describe_subject failed for {subject.name}: {e}')
