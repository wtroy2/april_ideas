"""
Claude (Anthropic) adapter — parallel implementation of the four text-gen
tasks (prompt polish, caption, scene planner, photo describe). Gemini Flash
is the default for each via settings (see providers/text.py); flip any task
to Claude by setting TEXT_*_MODEL=claude_sonnet.

Use Claude when you want richer creative voice — most valuable for captions.
For polish / planner / describe, the quality gap is small and Gemini is ~5×
cheaper, so there's rarely a reason to switch those.
"""

import base64
import json
import logging
import re

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
                "You are a viral pet content writer — the kind whose captions "
                "get screenshotted and shared. Playful, a little weird, "
                "sometimes deadpan, never corporate. Use specific details from "
                "the scenario; no generic praise. Vary sentence length. "
                "Output ONLY the caption text (no preamble, no surrounding "
                "quotes). Emojis sparse (1-2 max, often zero). End with 3-5 "
                "niche-specific hashtags."
            ),
            messages=[{'role': 'user', 'content': base}],
        )
        return response.content[0].text.strip()
    except Exception as e:
        logger.warning(f'Anthropic generate_caption failed: {e}')
        return ''


# ---------------------------------------------------------------------------
# Scene planner (StoryProject → list of scenes)
# ---------------------------------------------------------------------------

def plan_scenes(project):
    """Break a StoryProject's concept into a list of scenes.
    Returns [{"title", "prompt", "duration_seconds"}, …]."""
    subject = project.subject
    theme = project.theme

    target = max(4, project.target_duration_seconds or 30)
    per_scene = project.per_scene_duration_seconds or 8
    rough_count = max(2, min(10, round(target / per_scene)))

    fallback = [{
        'title': f'Scene 1: {project.concept[:80]}',
        'prompt': project.concept,
        'duration_seconds': per_scene,
    }]

    if not settings.ANTHROPIC_API_KEY:
        logger.warning('plan_scenes: ANTHROPIC_API_KEY not set, using fallback plan')
        return fallback

    theme_hint = ''
    if theme:
        theme_hint = (
            f'Overall style: {theme.name} — {theme.description}. '
            f'Shot style: {theme.get_shot_style_display()}. '
            f'Music vibe: {theme.get_music_vibe_display()}.'
        )

    system = (
        "You are a video story planner for short-form AI video generation. "
        "Break a user's concept into a sequence of short scenes (each a "
        "separate AI-generated clip) that will be stitched into one longer "
        "video. Write prompts optimized for Veo 3 / Runway Gen-4 / Kling: "
        "concrete, visual, specific — describe the shot, action, and setting. "
        "DO NOT write dialogue. DO NOT write cuts within a scene (each scene "
        "is one continuous shot). Output STRICT JSON only — an array of "
        "objects, no prose, no markdown fences."
    )

    user_msg = (
        f"Concept: {project.concept}\n"
        f"Subject: {subject.name}, a {subject.get_kind_display().lower()}"
        + (f" ({subject.get_species_display().lower()})" if subject.species else '')
        + f". Visual description: {subject.description or 'see prompts'}.\n"
        f"{theme_hint}\n"
        f"Target total duration: {target} seconds, split across approximately "
        f"{rough_count} scenes. Each scene is {per_scene} seconds.\n"
        + (f"Extra direction (applies to all scenes): {project.extra_detail}\n"
           if project.extra_detail else '')
        + f"\nReturn JSON like:\n"
          f'[\n'
          f'  {{"title": "Short label", "prompt": "Full visual description, 1-3 sentences", '
          f'"duration_seconds": {per_scene}}},\n'
          f"  ...\n"
          f']\n'
          f'Each scene flows visually to the next. Keep {subject.name} consistent throughout.'
    )

    try:
        client = _client()
        response = client.messages.create(
            model=DEFAULT_MODEL,
            max_tokens=3000,
            system=system,
            messages=[{'role': 'user', 'content': user_msg}],
        )
        raw = response.content[0].text.strip()
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```\s*$', '', raw)
        parsed = json.loads(raw)
        if not isinstance(parsed, list) or not parsed:
            raise ValueError(f'Planner returned non-list or empty: {raw[:200]}')

        scenes = []
        for i, item in enumerate(parsed):
            if not isinstance(item, dict):
                continue
            title = (item.get('title') or f'Scene {i + 1}')[:200]
            prompt = (item.get('prompt') or '').strip()
            if not prompt:
                continue
            duration = item.get('duration_seconds', per_scene)
            if duration not in (4, 6, 8):
                duration = per_scene
            scenes.append({'title': title, 'prompt': prompt, 'duration_seconds': duration})

        if not scenes:
            raise ValueError('No usable scenes in Claude response')

        logger.info(f'Claude planned {len(scenes)} scenes for story {project.uuid}')
        return scenes
    except Exception as e:
        logger.exception(f'Claude plan_scenes failed, using fallback: {e}')
        return fallback


# ---------------------------------------------------------------------------
# Subject photo description (Claude vision)
# ---------------------------------------------------------------------------

def describe_subject_from_photos(subject, photo_assets) -> str:
    """Claude-vision equivalent of the Gemini version. Downloads photos from
    GCS, passes as image content blocks, returns a ~30-word visual description."""
    if not photo_assets:
        return _fallback_description(subject)
    if not settings.ANTHROPIC_API_KEY:
        return _fallback_description(subject)

    selected = photo_assets[:6]
    from assets.storage import get_gcs_client
    gcs = get_gcs_client()
    image_blocks = []
    for asset in selected:
        try:
            blob = gcs.bucket(asset.bucket).blob(asset.object_key)
            data = blob.download_as_bytes()
            image_blocks.append({
                'type': 'image',
                'source': {
                    'type': 'base64',
                    'media_type': asset.content_type or 'image/jpeg',
                    'data': base64.b64encode(data).decode('ascii'),
                },
            })
        except Exception as e:
            logger.warning(f'Could not download {asset.uuid}: {e}')

    if not image_blocks:
        return _fallback_description(subject)

    prompt_text = (
        f'Look at these photos of a {subject.get_kind_display().lower()} named '
        f'"{subject.name}". '
        + (f'It is a {subject.get_species_display().lower()}. ' if subject.species else '')
        + 'Write a single concise visual description (1-2 sentences, ~30 words) '
          'that captures the visual identity — color, distinguishing features, '
          'build. Skip personality. Skip the name. Output only the description.'
    )

    try:
        client = _client()
        response = client.messages.create(
            model=DEFAULT_MODEL,
            max_tokens=200,
            messages=[{
                'role': 'user',
                'content': image_blocks + [{'type': 'text', 'text': prompt_text}],
            }],
        )
        text = response.content[0].text.strip()
        return text or _fallback_description(subject)
    except Exception as e:
        logger.error(f'Claude describe failed for {subject.name}: {e}')
        return _fallback_description(subject)


def _fallback_description(subject):
    parts = []
    if subject.species:
        parts.append(f'a {subject.get_species_display().lower()}')
    elif subject.kind:
        parts.append(f'a {subject.get_kind_display().lower()}')
    return f'{subject.name}, {", ".join(parts) or "the subject"}.'
