"""
Runway Gen-4 adapter — character-consistent video generation via the
References API. Used as the fallback when Veo doesn't keep the subject
consistent enough across a batch.

Targets the Runway public REST API: https://api.dev.runwayml.com/
Uses RUNWAY_API_KEY from settings.
"""

import base64
import logging
import time
from io import BytesIO
from typing import List, Optional

import requests
from django.conf import settings
from PIL import Image as PILImage

from .base import VideoProvider, VideoGenerationResult, VideoGenerationError

logger = logging.getLogger('providers')

RUNWAY_BASE_URL = 'https://api.dev.runwayml.com/v1'

# Max dimension + JPEG quality for the data-URL-encoded reference image.
# Runway's API drops connections on requests that are too large (common with
# raw phone photos at 3000×4000). Shrinking to 1024 on the long side keeps
# the body well under 1MB while still giving Runway plenty of detail.
RUNWAY_IMAGE_MAX_DIM = 1024
RUNWAY_IMAGE_QUALITY = 85


def _prepare_reference_image(image_bytes: bytes) -> str:
    """Resize + JPEG-recompress the reference image, return a data URL."""
    try:
        img = PILImage.open(BytesIO(image_bytes))
        if img.mode != 'RGB':
            img = img.convert('RGB')
        if max(img.size) > RUNWAY_IMAGE_MAX_DIM:
            img.thumbnail((RUNWAY_IMAGE_MAX_DIM, RUNWAY_IMAGE_MAX_DIM), PILImage.LANCZOS)
        buf = BytesIO()
        img.save(buf, format='JPEG', quality=RUNWAY_IMAGE_QUALITY, optimize=True)
        shrunk = buf.getvalue()
        logger.info(
            f'Runway: shrunk reference image from {len(image_bytes)} → '
            f'{len(shrunk)} bytes ({img.size[0]}×{img.size[1]})'
        )
        return 'data:image/jpeg;base64,' + base64.b64encode(shrunk).decode('ascii')
    except Exception as e:
        logger.warning(f'Runway image resize failed, falling back to raw: {e}')
        return 'data:image/jpeg;base64,' + base64.b64encode(image_bytes).decode('ascii')


class RunwayProvider(VideoProvider):
    name = 'runway'

    DEFAULT_MODEL_ID = 'gen4_turbo'

    # Models that support text-to-video (no reference image required).
    # Older models (gen3a_turbo, gen4_turbo) are strictly image-to-video.
    TEXT_TO_VIDEO_MODELS = {'gen4_5_turbo'}

    def __init__(self, model_id: Optional[str] = None):
        self.api_key = settings.RUNWAY_API_KEY
        self.MODEL_ID = model_id or self.DEFAULT_MODEL_ID
        if not self.api_key:
            logger.warning('Runway provider: RUNWAY_API_KEY not set')

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
        person_generation: str = 'dont_allow',  # accepted but unused — Runway moderates server-side
    ) -> VideoGenerationResult:
        if not self.api_key:
            raise VideoGenerationError('RUNWAY_API_KEY not configured')

        # Pick the right endpoint based on what we have:
        #   - Image provided → image_to_video (all Runway video models support this)
        #   - No image + model supports text-to-video (gen4_5) → text_to_video
        #   - No image + image-only model (gen3, gen4) → error
        supports_text = self.MODEL_ID in self.TEXT_TO_VIDEO_MODELS

        # Runway only supports 5s or 10s — snap our generic 4/6/8 to the closest.
        runway_duration = 10 if duration_seconds >= 9 else 5
        runway_ratio = self._to_runway_ratio(aspect_ratio)

        if reference_image_bytes:
            endpoint = '/image_to_video'
            payload = {
                'model': self.MODEL_ID,
                'promptText': prompt,
                'duration': runway_duration,
                'ratio': runway_ratio,
                'promptImage': _prepare_reference_image(reference_image_bytes[0]),
            }
        elif supports_text:
            endpoint = '/text_to_video'
            payload = {
                'model': self.MODEL_ID,
                'promptText': prompt,
                'duration': runway_duration,
                'ratio': runway_ratio,
            }
        else:
            raise VideoGenerationError(
                f"Runway model '{self.MODEL_ID}' requires a reference image, but "
                f"this subject has no photos uploaded. Upload one on the pet's "
                f"profile page, or pick Runway Gen-4.5 (supports text-only)."
            )

        if seed is not None:
            payload['seed'] = seed

        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
            'X-Runway-Version': '2024-11-06',
        }

        logger.info(f'Runway ({self.MODEL_ID}): starting generation via {endpoint}, prompt[:120]={prompt[:120]!r}')
        # Retry once on a transient network drop — Runway occasionally closes the
        # connection mid-POST when the payload is large or the server is warming.
        last_err = None
        r = None
        for attempt in range(2):
            try:
                r = requests.post(
                    f'{RUNWAY_BASE_URL}{endpoint}',
                    json=payload, headers=headers, timeout=120,
                )
                break
            except requests.exceptions.ConnectionError as e:
                last_err = e
                logger.warning(f'Runway POST failed (attempt {attempt + 1}/2): {e}')
                if attempt == 0:
                    time.sleep(2)
        if r is None:
            raise VideoGenerationError(
                f'Runway connection failed: {last_err}. '
                f'If this keeps happening, the reference image may be too large '
                f'or Runway may be having issues.'
            )
        if r.status_code >= 400:
            raise VideoGenerationError(f'Runway API error {r.status_code}: {r.text[:500]}')

        task_id = r.json().get('id')
        if not task_id:
            raise VideoGenerationError(f'Runway returned no task id: {r.text[:500]}')

        # Poll
        deadline = time.monotonic() + 600  # 10 min cap
        while True:
            if time.monotonic() > deadline:
                raise VideoGenerationError('Runway generation timed out after 10 minutes')
            time.sleep(8)
            poll = requests.get(f'{RUNWAY_BASE_URL}/tasks/{task_id}', headers=headers, timeout=30)
            poll.raise_for_status()
            data = poll.json()
            status = data.get('status')
            if status == 'SUCCEEDED':
                outputs = data.get('output') or []
                if not outputs:
                    raise VideoGenerationError('Runway succeeded but returned no outputs')
                video_url = outputs[0]
                video_bytes = requests.get(video_url, timeout=120).content
                return VideoGenerationResult(
                    video_bytes=video_bytes,
                    content_type='video/mp4',
                    duration_seconds=duration_seconds,
                    raw_response=data,
                )
            if status in ('FAILED', 'CANCELLED'):
                raise VideoGenerationError(f'Runway task {task_id} {status}: {data}')
            # PENDING / RUNNING — keep polling

    @staticmethod
    def _to_runway_ratio(aspect: str) -> str:
        """
        Map our generic aspect choices to Runway's accepted values.

        Gen-3 Alpha Turbo requires the pixel-dimension format specifically
        (768:1280 or 1280:768); Gen-4+ accepts either that or the generic
        form. Sending pixel dims everywhere works across all Runway models.

        Runway does NOT support 1:1 → fall back to portrait.
        """
        return {
            '9:16': '768:1280',
            '16:9': '1280:768',
            '1:1':  '768:1280',   # no square support → portrait
        }.get(aspect, '768:1280')
