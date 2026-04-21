"""
Gemini Vision adapter — looks at a Subject's reference photos and returns a
short structured visual description that gets injected into video prompts.

Output target: 1-2 sentences, ~30 words. Examples:
  - "Orange tabby cat with white chest patch and bright green eyes; medium build."
  - "Black and white border collie, fluffy coat, pink tongue often visible."

We don't try to capture personality — just visual identity, since that's what
the video model needs to keep consistent.
"""

import logging
from typing import List
from django.conf import settings

logger = logging.getLogger('providers')


def describe_subject_from_photos(subject, photo_assets) -> str:
    """
    Fetch the photos from GCS and ask Gemini to describe the subject.
    `photo_assets` is a list of Asset rows.
    """
    try:
        from google import genai
        from google.genai import types as genai_types
    except ImportError as e:
        logger.warning(f'google-genai not installed: {e}')
        return _fallback_description(subject)

    if not photo_assets:
        return _fallback_description(subject)

    # Use up to 6 photos to keep latency + cost reasonable
    selected = photo_assets[:6]

    # Download bytes from GCS
    from assets.storage import get_gcs_client
    client_gcs = get_gcs_client()
    image_parts = []
    for asset in selected:
        try:
            blob = client_gcs.bucket(asset.bucket).blob(asset.object_key)
            data = blob.download_as_bytes()
            image_parts.append(genai_types.Part.from_bytes(
                data=data, mime_type=asset.content_type or 'image/jpeg'
            ))
        except Exception as e:
            logger.warning(f'Could not download {asset.uuid} for describe: {e}')

    if not image_parts:
        return _fallback_description(subject)

    prompt_text = (
        f'Look at these photos of a {subject.get_kind_display().lower()} '
        f'named "{subject.name}". '
        + (f'It is a {subject.get_species_display().lower()}. ' if subject.species else '')
        + 'Write a single concise visual description (1-2 sentences, ~30 words) '
          'that captures the visual identity — color, distinguishing features, '
          'build. Skip personality. Skip the name. Output only the description.'
    )

    if not settings.VERTEX_CREDENTIALS:
        logger.warning('VERTEX_CREDENTIALS not configured, falling back to text description')
        return _fallback_description(subject)

    try:
        # Explicit Vertex AI mode + service account credentials —
        # never fall back to gcloud user, never call AI Studio.
        client = genai.Client(
            vertexai=True,
            project=settings.GOOGLE_CLOUD_PROJECT_ID,
            location=settings.GOOGLE_CLOUD_GEMINI_LOCATION,
            credentials=settings.VERTEX_CREDENTIALS,
        )
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[
                genai_types.Content(
                    role='user',
                    parts=image_parts + [genai_types.Part.from_text(text=prompt_text)],
                ),
            ],
        )
        text = (response.text or '').strip()
        return text or _fallback_description(subject)
    except Exception as e:
        logger.error(f'Gemini describe failed for subject {subject.name}: {e}')
        return _fallback_description(subject)


def _fallback_description(subject):
    """Best-effort description when Gemini isn't available."""
    parts = []
    if subject.species:
        parts.append(f'a {subject.get_species_display().lower()}')
    elif subject.kind:
        parts.append(f'a {subject.get_kind_display().lower()}')
    return f'{subject.name}, {", ".join(parts) or "the subject"}.'
