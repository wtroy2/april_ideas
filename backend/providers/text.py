"""
Text-generation dispatcher.

Four tasks in the pipeline need LLM-generated text:
  - Prompt polish   (batch + scene modes)
  - Caption writing
  - Scene planning
  - Subject photo description (vision: describes a pet from its photos)

Each is independently switchable between providers via settings:
  TEXT_POLISH_MODEL    — 'gemini_flash' | 'claude_sonnet'
  TEXT_CAPTION_MODEL   — 'gemini_flash' | 'claude_sonnet'
  TEXT_PLANNER_MODEL   — 'gemini_flash' | 'claude_sonnet'
  TEXT_DESCRIBE_MODEL  — 'gemini_flash' | 'claude_sonnet'

Defaults are Gemini Flash everywhere — ~5× cheaper than Claude Sonnet, uses
the existing Vertex AI service account so there's no separate billing
pipeline. Flip any one task to Claude by setting the matching env var in
.env (and ensure ANTHROPIC_API_KEY is funded).

Callers always import from this module — never directly from gemini_text
or anthropic_text — so swapping is a settings change, not a code change.
"""

import logging
from django.conf import settings

logger = logging.getLogger('providers')

_VALID_MODELS = {'gemini_flash', 'claude_sonnet'}


def _backend_for(task: str):
    """Return the module implementing the text-gen functions for the given task."""
    setting_key = {
        'polish':   'TEXT_POLISH_MODEL',
        'caption':  'TEXT_CAPTION_MODEL',
        'planner':  'TEXT_PLANNER_MODEL',
        'describe': 'TEXT_DESCRIBE_MODEL',
    }[task]
    name = getattr(settings, setting_key, 'gemini_flash')
    if name not in _VALID_MODELS:
        logger.warning(f'Unknown {setting_key}={name!r}, defaulting to gemini_flash')
        name = 'gemini_flash'

    if name == 'claude_sonnet':
        from . import anthropic_text as mod
    else:
        from . import gemini_text as mod
    return mod


# ---------------------------------------------------------------------------
# Public API — matches both provider modules' signatures.
# ---------------------------------------------------------------------------

def expand_prompt(*, theme, subject, scenario, detail=''):
    """Render + polish a theme template. Used in batch mode."""
    return _backend_for('polish').expand_prompt(
        theme=theme, subject=subject, scenario=scenario, detail=detail,
    )


def polish_prompt(raw_prompt, *, subject=None):
    """Polish an already-full prompt. Used in story scene mode."""
    return _backend_for('polish').polish_prompt(raw_prompt, subject=subject)


def generate_caption(*, theme, subject, scenario, detail=''):
    """Write an IG/TikTok caption for a succeeded generation."""
    return _backend_for('caption').generate_caption(
        theme=theme, subject=subject, scenario=scenario, detail=detail,
    )


def plan_scenes(project):
    """Break a StoryProject's concept into an ordered list of scenes."""
    return _backend_for('planner').plan_scenes(project)


def describe_subject_from_photos(subject, photo_assets):
    """Look at a subject's reference photos and return a visual description."""
    return _backend_for('describe').describe_subject_from_photos(subject, photo_assets)
