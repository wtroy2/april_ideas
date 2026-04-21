"""
Gemini 2.5 Flash adapter for prompt polishing + caption writing + scene
planning. Drop-in replacement for the Anthropic module, using the same
Vertex AI credentials as our Veo and image-describe calls — so no separate
API key, no separate billing, zero workspace confusion.

Cost: ~$0.30/M input, $2.50/M output. Per video cost for prompt polish +
caption is ~$0.002 (5× cheaper than Claude Sonnet).
"""

import json
import logging
import re

from django.conf import settings

logger = logging.getLogger('providers')

DEFAULT_MODEL = 'gemini-2.5-flash'


def _client():
    """Build a Gemini client using the Critter service account via Vertex AI."""
    from google import genai
    if not settings.VERTEX_CREDENTIALS:
        raise RuntimeError('VERTEX_CREDENTIALS not configured')
    return genai.Client(
        vertexai=True,
        project=settings.GOOGLE_CLOUD_PROJECT_ID,
        location=settings.GOOGLE_CLOUD_GEMINI_LOCATION,
        credentials=settings.VERTEX_CREDENTIALS,
    )


def _generate(
    system: str,
    user: str,
    max_tokens: int = 400,
    temperature: float = 0.9,
    json_mode: bool = False,
) -> str:
    """Small internal helper — one-shot generate with system + user parts.

    Default temperature is 0.9 (bumped from 0.7) so Flash outputs feel less
    templated / more like Claude-style creative prose. Tasks that need
    determinism (planner, describe) override to lower values.
    """
    from google.genai import types
    client = _client()
    config_kwargs = {
        'system_instruction': system,
        'max_output_tokens': max_tokens,
        'temperature': temperature,
    }
    if json_mode:
        config_kwargs['response_mime_type'] = 'application/json'
    response = client.models.generate_content(
        model=DEFAULT_MODEL,
        contents=user,
        config=types.GenerateContentConfig(**config_kwargs),
    )
    return (response.text or '').strip()


# ---------------------------------------------------------------------------
# Prompt polishing (batch + scene modes)
# ---------------------------------------------------------------------------

_PROMPT_SYSTEM = (
    "You are a video prompt engineer. Take the user's draft video prompt and "
    "rewrite it into a single concise paragraph (60-120 words) optimized for "
    "Veo 3 / Runway Gen-4 / Kling. Preserve all subject, scene, and action "
    "details from the draft. Keep it cinematic but specific — describe the "
    "shot, action, lighting, and setting. No dialogue. No cuts/edits within "
    "the scene. Output the prompt only — no preamble, no markdown."
)


def expand_prompt(*, theme, subject, scenario, detail=''):
    """Render theme template + subject + scenario, then let Gemini polish it.
    Used by batch mode (New Batch page)."""
    base = theme.render_prompt(subject=subject, scenario=scenario, detail=detail)
    try:
        # temp=0.9 — creative but still constrained by the template content
        polished = _generate(_PROMPT_SYSTEM, base, max_tokens=400, temperature=0.9)
        return polished or base
    except Exception as e:
        logger.warning(f'Gemini expand_prompt failed, falling back to template: {e}')
        return base


def polish_prompt(raw_prompt, *, subject=None):
    """Polish an already-full prompt (story scene mode — scene.prompt is
    already complete, no template to render)."""
    system = _PROMPT_SYSTEM
    if subject and subject.description:
        system += f' Main character: {subject.name} — {subject.description}.'
    try:
        polished = _generate(system, raw_prompt, max_tokens=400, temperature=0.9)
        return polished or raw_prompt
    except Exception as e:
        logger.warning(f'Gemini polish_prompt failed, falling back to raw: {e}')
        return raw_prompt


# ---------------------------------------------------------------------------
# Caption generation
# ---------------------------------------------------------------------------

_CAPTION_SYSTEM = (
    "You are a viral pet content writer — the kind whose captions get "
    "screenshotted and shared. Your voice is playful, a little bit weird, "
    "sometimes deadpan, never corporate. Write captions that sound like a "
    "real person who adores their pet and has a sense of humor. Use "
    "specific details from the scenario — not generic praise. Vary your "
    "sentence length. Occasional all-caps for emphasis is fine. "
    "\n\n"
    "Output ONLY the caption text — no preamble, no quotes around it. "
    "Keep emojis sparse (1-2 max, often zero). End with 3-5 niche-specific "
    "hashtags. Aim for 1-3 short lines."
)


def generate_caption(*, theme, subject, scenario, detail=''):
    """Caption for an Instagram/TikTok post built on a batch generation."""
    base = theme.render_caption_prompt(subject=subject, scenario=scenario, detail=detail)
    if not base:
        return ''
    try:
        # temp=1.0 — voice matters most here, push for variety
        return _generate(_CAPTION_SYSTEM, base, max_tokens=300, temperature=1.0)
    except Exception as e:
        logger.warning(f'Gemini generate_caption failed: {e}')
        return ''


# ---------------------------------------------------------------------------
# Story scene planner — returns a list of {title, prompt, duration_seconds}
# ---------------------------------------------------------------------------

_PLANNER_SYSTEM = (
    "You are a video story planner for short-form AI video generation. Break "
    "a user's concept into a sequence of short scenes (each a separate "
    "AI-generated clip) that will be stitched together into one longer "
    "video. Write prompts optimized for Veo 3 / Runway Gen-4 / Kling: "
    "concrete, visual, specific — describe the shot, action, and setting. "
    "Do NOT write dialogue. Do NOT include cuts within a scene (each scene "
    "is one continuous shot). Output STRICT JSON only — an array of "
    "objects, no prose, no markdown fences."
)


def plan_scenes(project):
    """
    Plan scenes for a StoryProject — returns a list of dicts:
      [{"title": ..., "prompt": ..., "duration_seconds": 4|6|8}, ...]

    Never raises — returns a 1-scene fallback if anything goes wrong so the
    story workflow isn't blocked.
    """
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

    if not settings.VERTEX_CREDENTIALS:
        logger.warning('plan_scenes: VERTEX_CREDENTIALS not set, using fallback plan')
        return fallback

    theme_hint = ''
    if theme:
        theme_hint = (
            f'Overall style: {theme.name} — {theme.description}. '
            f'Shot style: {theme.get_shot_style_display()}. '
            f'Music vibe: {theme.get_music_vibe_display()}.'
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
          f'  {{"title": "Short scene label", "prompt": "Full visual description, 1-3 sentences", '
          f'"duration_seconds": {per_scene}}},\n'
          f"  ...\n"
          f']\n'
          f'Each scene should flow visually to the next. Keep {subject.name} as the '
          f'consistent character throughout.'
    )

    try:
        # temp=0.7 — structured output, want less variance
        raw = _generate(_PLANNER_SYSTEM, user_msg, max_tokens=3000, temperature=0.7, json_mode=True)
        # Defensive stripping in case Gemini wraps in a fence despite json_mode
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
            raise ValueError('No usable scenes in Gemini response')

        logger.info(f'Planned {len(scenes)} scenes for story {project.uuid}')
        return scenes

    except Exception as e:
        logger.exception(f'plan_scenes failed, using fallback: {e}')
        return fallback


# ---------------------------------------------------------------------------
# Subject auto-description from reference photos
# ---------------------------------------------------------------------------

def describe_subject_from_photos(subject, photo_assets) -> str:
    """
    Ask Gemini Vision to look at the subject's reference photos and produce
    a concise visual description used in every video prompt.

    Output target: 1-2 sentences, ~30 words. Captures visual identity only
    (color, markings, build, eyes) — no personality. Drives consistency
    across batch generations when the model is working from the prompt alone
    (i.e., user has `use_photo_background=False` set).
    """
    try:
        from google import genai
        from google.genai import types as genai_types
    except ImportError as e:
        logger.warning(f'google-genai not installed: {e}')
        return _fallback_description(subject)

    if not photo_assets:
        return _fallback_description(subject)
    if not settings.VERTEX_CREDENTIALS:
        return _fallback_description(subject)

    selected = photo_assets[:6]
    from assets.storage import get_gcs_client
    gcs = get_gcs_client()
    image_parts = []
    for asset in selected:
        try:
            blob = gcs.bucket(asset.bucket).blob(asset.object_key)
            data = blob.download_as_bytes()
            image_parts.append(genai_types.Part.from_bytes(
                data=data, mime_type=asset.content_type or 'image/jpeg'
            ))
        except Exception as e:
            logger.warning(f'Could not download {asset.uuid}: {e}')

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

    try:
        client = _client()
        # temp=0.3 — descriptions should be accurate / stable across regenerations
        response = client.models.generate_content(
            model=DEFAULT_MODEL,
            contents=[
                genai_types.Content(
                    role='user',
                    parts=image_parts + [genai_types.Part.from_text(text=prompt_text)],
                ),
            ],
            config=genai_types.GenerateContentConfig(
                temperature=0.3, max_output_tokens=200,
            ),
        )
        text = (response.text or '').strip()
        return text or _fallback_description(subject)
    except Exception as e:
        logger.error(f'Gemini describe failed for {subject.name}: {e}')
        return _fallback_description(subject)


def _fallback_description(subject):
    """Best-effort label when the vision call is unavailable."""
    parts = []
    if subject.species:
        parts.append(f'a {subject.get_species_display().lower()}')
    elif subject.kind:
        parts.append(f'a {subject.get_kind_display().lower()}')
    return f'{subject.name}, {", ".join(parts) or "the subject"}.'
