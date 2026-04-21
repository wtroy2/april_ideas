"""
Veo 3 (Google Vertex AI) adapter — primary video generation.

Uses the Vertex AI long-running predict endpoint. Polls until the operation
returns a video, then downloads the bytes from GCS.

Note: the Veo API surface is still evolving. This adapter targets the public
Vertex AI Generative Models API as of early 2026 — `google-cloud-aiplatform >= 1.96`.
"""

import logging
import os
import time
import base64
from typing import List, Optional

from django.conf import settings

from .base import VideoProvider, VideoGenerationResult, VideoGenerationError

logger = logging.getLogger('providers')


class VeoProvider(VideoProvider):
    name = 'veo'

    # Default to Veo 3.1 Lite — cheapest tier. The factory in providers/__init__.py
    # passes a specific model_id per the user's selection on the New Batch page.
    DEFAULT_MODEL_ID = os.environ.get('VEO_MODEL_ID', 'veo-3.1-lite-generate-001')

    def __init__(self, model_id: Optional[str] = None):
        self.project = settings.GOOGLE_CLOUD_PROJECT_ID
        self.location = settings.GOOGLE_CLOUD_GEMINI_LOCATION
        self.MODEL_ID = model_id or self.DEFAULT_MODEL_ID

    def supports_reference_images(self) -> bool:
        return True

    def generate(
        self,
        *,
        prompt: str,
        reference_image_bytes: Optional[List[bytes]] = None,
        aspect_ratio: str = '9:16',
        duration_seconds: int = 8,
        seed: Optional[int] = None,
        # Safety lever Veo exposes:
        #   'dont_allow' — refuses to generate any human (default for pet subjects)
        #   'allow_adult' — adults only, no minors (default for person subjects)
        #   'allow_all' — everyone (only enable if gated behind ToS / age check)
        person_generation: str = 'dont_allow',
    ) -> VideoGenerationResult:
        try:
            from google import genai
            from google.genai import types as genai_types
        except ImportError as e:
            raise VideoGenerationError(f'google-genai not installed: {e}')

        # Explicit Vertex AI mode + service account credentials.
        # Never fall back to gcloud user, never call AI Studio.
        if not settings.VERTEX_CREDENTIALS:
            raise VideoGenerationError(
                'VERTEX_CREDENTIALS not configured (set GOOGLE_SA_KEYFILE in .env)'
            )
        client = genai.Client(
            vertexai=True,
            project=self.project,
            location=self.location,
            credentials=settings.VERTEX_CREDENTIALS,
        )

        gen_config = genai_types.GenerateVideosConfig(
            aspect_ratio=aspect_ratio,
            duration_seconds=duration_seconds,
            number_of_videos=1,
            generate_audio=True,
            resolution='720p',
            person_generation=person_generation,
        )
        if seed is not None:
            gen_config.seed = seed

        # Image-to-video: pass the first reference image as the seed frame.
        # Use the flat-arg pattern — works across SDK versions. The newer
        # GenerateVideosSource wrapper only exists in google-genai >= a recent
        # version we can't assume the user has.
        kwargs = {
            'model': self.MODEL_ID,
            'prompt': prompt,
            'config': gen_config,
        }
        if reference_image_bytes:
            kwargs['image'] = genai_types.Image(
                image_bytes=reference_image_bytes[0],
                mime_type='image/jpeg',
            )

        logger.info(f'Veo ({self.MODEL_ID}): generating, prompt[:120]={prompt[:120]!r}')
        try:
            operation = client.models.generate_videos(**kwargs)
        except Exception as e:
            msg = str(e)
            if '404' in msg or 'NOT_FOUND' in msg:
                raise VideoGenerationError(
                    f"Model '{self.MODEL_ID}' not found or your project doesn't have access. "
                    f"Request access at https://console.cloud.google.com/vertex-ai/model-garden "
                    f"or pick a different model in the New Batch dropdown. "
                    f"(veo-3.1-lite-generate-001 is usually accessible by default.)"
                ) from e
            raise

        # Poll the long-running op
        deadline = time.monotonic() + 300  # 5 min hard cap
        while not operation.done:
            if time.monotonic() > deadline:
                raise VideoGenerationError('Veo generation timed out after 5 minutes')
            time.sleep(8)
            operation = client.operations.get(operation)

        if operation.error:
            err_msg = operation.error.get('message', '') if isinstance(operation.error, dict) else str(operation.error)
            if 'duration' in err_msg.lower():
                raise VideoGenerationError(
                    f"Veo rejected the duration ({duration_seconds}s). Supported values are 4, 6, or 8. "
                    f"Original error: {err_msg}"
                )
            raise VideoGenerationError(f'Veo error: {operation.error}')

        # Find the videos in the response — SDK has shifted attribute names across
        # versions, so try the known paths in order.
        videos = (
            getattr(operation, 'result', None) and getattr(operation.result, 'generated_videos', None)
            or getattr(operation, 'result', None) and getattr(operation.result, 'videos', None)
            or getattr(operation, 'response', None) and getattr(operation.response, 'generated_videos', None)
            or getattr(operation, 'response', None) and getattr(operation.response, 'videos', None)
            or []
        )

        if not videos:
            # Could be a safety filter (RAI). Check for a filter reason and surface it.
            rai_reason = (
                _peek(operation, 'result.rai_media_filtered_reason')
                or _peek(operation, 'result.rai_media_filtered_count')
                or _peek(operation, 'response.rai_media_filtered_reason')
            )
            # Dump the full result for debugging — Veo's response shape changes often
            try:
                dump = repr(getattr(operation, 'result', None) or getattr(operation, 'response', None))[:1500]
            except Exception:
                dump = '(could not repr operation result)'
            logger.error(f'Veo returned no videos. Operation result: {dump}')

            if rai_reason:
                raise VideoGenerationError(
                    f"Veo blocked the output via the people/face safety filter — "
                    f"the prompt implied a human but the safety setting forbade it. "
                    f"Fix: on the New Batch page → Options → 'People in videos' → "
                    f"choose 'Allow people (recommended)' so the prompt and Veo "
                    f"agree, then re-run. Veo's reason: {rai_reason}"
                )
            raise VideoGenerationError(
                'Veo returned no videos (no error, no RAI reason). '
                'Check the server log for the raw operation dump.'
            )

        first = videos[0]
        video = getattr(first, 'video', None) or first
        # Veo returns either inline bytes or a GCS URI
        video_bytes = getattr(video, 'video_bytes', None)
        if video_bytes is None:
            uri = getattr(video, 'uri', None)
            if not uri:
                raise VideoGenerationError('Veo returned no video bytes or URI')
            video_bytes = self._download_from_gcs_uri(uri)

        return VideoGenerationResult(
            video_bytes=video_bytes,
            content_type='video/mp4',
            duration_seconds=duration_seconds,
        )

    def _download_from_gcs_uri(self, uri: str) -> bytes:
        """Download bytes from a gs:// URI using the configured GCS credentials."""
        from assets.storage import get_gcs_client
        if not uri.startswith('gs://'):
            raise VideoGenerationError(f'Unexpected video URI: {uri}')
        path = uri[len('gs://'):]
        bucket_name, _, key = path.partition('/')
        client = get_gcs_client()
        return client.bucket(bucket_name).blob(key).download_as_bytes()


def _peek(obj, dotted_path: str):
    """Safely traverse `obj.a.b.c` from a dotted string. Returns None on any miss."""
    cur = obj
    for attr in dotted_path.split('.'):
        cur = getattr(cur, attr, None)
        if cur is None:
            return None
    return cur
