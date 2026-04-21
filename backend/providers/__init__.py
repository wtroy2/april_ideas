"""
Providers — adapters for external AI services.

Layout:
  base.py            — abstract VideoProvider interface
  veo.py             — Vertex AI Veo 3 (primary video generation)
  runway.py          — Runway Gen-4 (character consistency fallback)
  anthropic_text.py  — Claude Sonnet for scripts and captions
  image_describe.py  — Gemini Vision for subject auto-description

The generation pipeline imports get_video_provider(name) and calls .generate().
Swap providers by changing the name in the generation row or the default in
settings.
"""

from .base import VideoProvider, VideoGenerationResult, VideoGenerationError


# Maps each generations.models.VideoProvider choice → actual model id.
# Update model IDs here when providers ship new versions; no code changes needed.
#
# Veo: only -001 GA suffixes work without an access request. Preview-suffixed
# (veo-3.1-generate-preview etc.) require allowlist via Vertex AI Model Garden:
#   https://console.cloud.google.com/vertex-ai/model-garden
VEO_MODEL_IDS = {
    'veo_31_lite': 'veo-3.1-lite-generate-001',  # confirmed working
    'veo_31_fast': 'veo-3.1-fast-generate-001',  # may need access request
    'veo_31':      'veo-3.1-generate-001',       # may need access request
    'veo_30_fast': 'veo-3.0-fast-generate-001',  # GA, usually accessible
    'veo_30':      'veo-3.0-generate-001',       # GA, usually accessible
}

RUNWAY_MODEL_IDS = {
    'runway_gen3':    'gen3a_turbo',    # legacy, cheapest
    'runway_gen4':    'gen4_turbo',     # current fastest image-to-video
    'runway_gen4_5':  'gen4_5_turbo',   # Gen-4.5 — state-of-the-art text+image to video
    'runway':         'gen4_turbo',     # legacy alias
}

KLING_MODEL_IDS = {
    'kling_21': 'kling-v2-1-master',  # Kling 2.1 Master tier (premium)
}


def get_video_provider(name='veo_31_lite'):
    """Factory — return a configured VideoProvider for the given choice code."""
    if name in VEO_MODEL_IDS:
        from .veo import VeoProvider
        return VeoProvider(model_id=VEO_MODEL_IDS[name])
    if name in RUNWAY_MODEL_IDS:
        from .runway import RunwayProvider
        return RunwayProvider(model_id=RUNWAY_MODEL_IDS[name])
    if name in KLING_MODEL_IDS:
        from .kling import KlingProvider
        return KlingProvider(model_id=KLING_MODEL_IDS[name])
    raise ValueError(f'Unknown video provider: {name}')


__all__ = [
    'VideoProvider',
    'VideoGenerationResult',
    'VideoGenerationError',
    'get_video_provider',
]
