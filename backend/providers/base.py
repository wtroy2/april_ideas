"""Abstract base for video providers (Veo, Runway, etc)."""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class VideoGenerationResult:
    """What every provider returns from .generate()."""
    video_bytes: bytes
    content_type: str = 'video/mp4'
    duration_seconds: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    raw_response: Optional[dict] = None


class VideoGenerationError(Exception):
    """Raised when a provider fails to generate."""


class VideoProvider:
    """
    Subclass and implement .generate(). Each call should be synchronous from
    the caller's perspective — providers internally poll their long-running
    operation if needed and return only when the video bytes are ready.
    """

    name: str = 'unknown'

    def generate(
        self,
        *,
        prompt: str,
        reference_image_bytes: Optional[List[bytes]] = None,
        aspect_ratio: str = '9:16',
        duration_seconds: int = 8,
        seed: Optional[int] = None,
        person_generation: str = 'dont_allow',
    ) -> VideoGenerationResult:
        raise NotImplementedError

    def supports_reference_images(self) -> bool:
        return False
