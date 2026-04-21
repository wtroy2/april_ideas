"""
Claude (Anthropic) adapter — used for prompt expansion and caption polishing.

Pattern: keep these calls thin and synchronous. Generations call
`generate_caption(theme, subject, scenario)` after the video is in hand.
"""

import logging
from django.conf import settings

logger = logging.getLogger('providers')

DEFAULT_MODEL = 'claude-sonnet-4-6'  # latest Sonnet


def _client():
    try:
        import anthropic
    except ImportError as e:
        raise RuntimeError(f'anthropic SDK not installed: {e}')
    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError('ANTHROPIC_API_KEY not configured')
    return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)


def expand_prompt(*, theme, subject, scenario, detail=''):
    """
    Take the theme's prompt template + subject info + scenario, and let Claude
    expand it into a richer, more cinematic video prompt. Optional — the raw
    template works fine; this just polishes.
    """
    base = theme.render_prompt(subject=subject, scenario=scenario, detail=detail)
    try:
        client = _client()
        response = client.messages.create(
            model=DEFAULT_MODEL,
            max_tokens=400,
            system=(
                'You are a video prompt engineer. Take the user\'s draft video prompt '
                'and rewrite it into a single concise paragraph (60-120 words) that\'s '
                'optimized for Veo 3 / Runway Gen-4. Preserve all subject details and '
                'scenario specifics. Keep it cinematic but specific. Output the prompt only — '
                'no preamble.'
            ),
            messages=[{'role': 'user', 'content': base}],
        )
        text = response.content[0].text.strip()
        return text or base
    except Exception as e:
        logger.warning(f'Anthropic expand_prompt failed, falling back to template: {e}')
        return base


def polish_prompt(raw_prompt, *, subject=None):
    """
    Lightly polish an already-assembled prompt (from a story scene) for video
    gen. Same shape as expand_prompt but doesn't take a theme template.
    """
    try:
        client = _client()
        subject_hint = ''
        if subject and subject.description:
            subject_hint = f' Main character: {subject.name} — {subject.description}.'
        response = client.messages.create(
            model=DEFAULT_MODEL,
            max_tokens=400,
            system=(
                'You are a video prompt engineer. Rewrite the user\'s draft '
                'video prompt into a single concise paragraph (60-120 words) '
                'optimized for Veo 3 / Runway Gen-4 / Kling. Preserve all '
                'subject, scene, and action details; keep it visual and '
                'specific; no dialogue, no edits/cuts. Output the prompt only.'
                + subject_hint
            ),
            messages=[{'role': 'user', 'content': raw_prompt}],
        )
        text = response.content[0].text.strip()
        return text or raw_prompt
    except Exception as e:
        logger.warning(f'polish_prompt failed, using raw: {e}')
        return raw_prompt


def generate_caption(*, theme, subject, scenario, detail=''):
    """Generate a social caption (Instagram/TikTok) for the finished video."""
    base = theme.render_caption_prompt(subject=subject, scenario=scenario, detail=detail)
    if not base:
        return ''
    try:
        client = _client()
        response = client.messages.create(
            model=DEFAULT_MODEL,
            max_tokens=300,
            system=(
                'You are a viral pet content writer. Output ONLY the caption text — '
                'no preamble, no quotes around it. Keep emojis sparse (1-2 max).'
            ),
            messages=[{'role': 'user', 'content': base}],
        )
        return response.content[0].text.strip()
    except Exception as e:
        logger.warning(f'Anthropic generate_caption failed: {e}')
        return ''
