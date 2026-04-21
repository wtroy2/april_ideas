"""
Kling 2.1 (Kuaishou) adapter — premium cinematic video generation.

Auth: HS256 JWT signed with KLING_SECRET_KEY, issuer = KLING_ACCESS_KEY,
30-minute expiry. Sent as `Authorization: Bearer <jwt>`.

Endpoints (https://docs.qingque.cn/d/home/eZQDD0bFOpdOuCDVTr-OBZRej):
  POST /v1/videos/text2video       — text-only
  POST /v1/videos/image2video      — with reference image
  GET  /v1/videos/{kind}/{task_id} — poll status

Model IDs we use:
  - kling-v2-1-master  (premium tier, ~$1.40 / 5-sec clip)
  - kling-v2-1         (standard tier)
  - kling-v1-6 / v1-5  (older, cheaper)

If you don't have Kling credentials, set KLING_ACCESS_KEY + KLING_SECRET_KEY
in backend/.env (sign up at klingai.com → Developer Console).
"""

import base64
import logging
import time
from typing import List, Optional

import jwt
import requests
from django.conf import settings

from .base import VideoProvider, VideoGenerationResult, VideoGenerationError

logger = logging.getLogger('providers')

KLING_BASE_URL = 'https://api.klingai.com'


class KlingProvider(VideoProvider):
    name = 'kling'

    DEFAULT_MODEL_ID = 'kling-v2-1-master'

    def __init__(self, model_id: Optional[str] = None):
        self.access_key = getattr(settings, 'KLING_ACCESS_KEY', '')
        self.secret_key = getattr(settings, 'KLING_SECRET_KEY', '')
        self.MODEL_ID = model_id or self.DEFAULT_MODEL_ID
        if not (self.access_key and self.secret_key):
            logger.warning('Kling provider: KLING_ACCESS_KEY / KLING_SECRET_KEY not set')

    def supports_reference_images(self) -> bool:
        return True

    def _make_token(self) -> str:
        """30-minute JWT for Kling — token works for any number of API calls in that window."""
        now = int(time.time())
        payload = {'iss': self.access_key, 'exp': now + 1800, 'nbf': now - 5}
        return jwt.encode(
            payload, self.secret_key, algorithm='HS256',
            headers={'alg': 'HS256', 'typ': 'JWT'},
        )

    def generate(
        self,
        *,
        prompt: str,
        reference_image_bytes: Optional[List[bytes]] = None,
        aspect_ratio: str = '9:16',
        duration_seconds: int = 8,
        seed: Optional[int] = None,
        # Kling moderates server-side; argument accepted for interface symmetry.
        person_generation: str = 'allow_adult',
    ) -> VideoGenerationResult:
        if not (self.access_key and self.secret_key):
            raise VideoGenerationError('KLING_ACCESS_KEY / KLING_SECRET_KEY not configured')

        # Kling supports 5 or 10 seconds. Snap our generic 4/6/8 to the closest valid.
        kling_duration = 10 if duration_seconds >= 9 else 5

        endpoint = '/v1/videos/text2video'
        body = {
            'model_name': self.MODEL_ID,
            'prompt': prompt[:2500],   # Kling caps prompt length
            'duration': str(kling_duration),
            'aspect_ratio': self._to_kling_ratio(aspect_ratio),
            'mode': 'pro',  # 'std' for standard, 'pro' for higher quality (cost varies)
        }

        if reference_image_bytes:
            endpoint = '/v1/videos/image2video'
            body['image'] = base64.b64encode(reference_image_bytes[0]).decode('ascii')

        if seed is not None:
            body['seed'] = seed

        url = f'{KLING_BASE_URL}{endpoint}'
        headers = {
            'Authorization': f'Bearer {self._make_token()}',
            'Content-Type': 'application/json',
        }

        logger.info(f'Kling ({self.MODEL_ID}): submitting, prompt[:120]={prompt[:120]!r}')
        r = requests.post(url, json=body, headers=headers, timeout=60)
        if r.status_code >= 400:
            raise VideoGenerationError(f'Kling API error {r.status_code}: {r.text[:500]}')

        data = r.json()
        task_id = (data.get('data') or {}).get('task_id')
        if not task_id:
            raise VideoGenerationError(f'Kling returned no task id: {data}')

        # Poll
        kind = 'image2video' if reference_image_bytes else 'text2video'
        poll_url = f'{KLING_BASE_URL}/v1/videos/{kind}/{task_id}'
        deadline = time.monotonic() + 900  # 15 min cap (Kling can be slow on Pro tier)
        while True:
            if time.monotonic() > deadline:
                raise VideoGenerationError('Kling generation timed out after 15 minutes')
            time.sleep(10)

            # Refresh token in case the original expired during a long generation
            poll = requests.get(
                poll_url,
                headers={'Authorization': f'Bearer {self._make_token()}'},
                timeout=30,
            )
            if poll.status_code >= 400:
                logger.warning(f'Kling poll error {poll.status_code}, retrying: {poll.text[:200]}')
                continue

            poll_data = poll.json()
            inner = poll_data.get('data') or {}
            status = inner.get('task_status')
            if status == 'succeed':
                videos = (inner.get('task_result') or {}).get('videos') or []
                if not videos:
                    raise VideoGenerationError('Kling succeeded but returned no videos')
                video_url = videos[0].get('url')
                if not video_url:
                    raise VideoGenerationError(f'Kling video has no URL: {videos[0]}')
                video_bytes = requests.get(video_url, timeout=120).content
                return VideoGenerationResult(
                    video_bytes=video_bytes,
                    content_type='video/mp4',
                    duration_seconds=kling_duration,
                    raw_response=poll_data,
                )
            if status == 'failed':
                msg = inner.get('task_status_msg') or '(no message)'
                raise VideoGenerationError(f'Kling task {task_id} failed: {msg}')
            # 'submitted' / 'processing' — keep polling

    @staticmethod
    def _to_kling_ratio(aspect: str) -> str:
        # Kling supports 16:9, 9:16, 1:1 strings literally.
        return {'9:16': '9:16', '16:9': '16:9', '1:1': '1:1'}.get(aspect, '9:16')
