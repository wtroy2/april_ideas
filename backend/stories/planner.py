"""
Claude-powered scene planner.

Given a StoryProject (concept + subject + theme + target duration), produces
a structured list of scenes the user can review and edit before we generate
anything. Each scene has a title, a Veo-ready prompt, and a duration.

The planner is best-effort — if Claude isn't configured or fails, we return
a fallback single-scene plan from the raw concept so the user isn't blocked.
"""

import json
import logging
import re
from typing import List

from django.conf import settings

logger = logging.getLogger('stories')

DEFAULT_MODEL = 'claude-sonnet-4-6'


def plan_scenes(project) -> List[dict]:
    """
    Return a list of {title, prompt, duration_seconds} dicts ordered by scene.
    Guarantees at least one scene. Never raises — falls back to a concept-only
    single scene if anything goes wrong.
    """
    subject = project.subject
    theme = project.theme

    # How many scenes to aim for, given the target and per-scene duration
    target = max(4, project.target_duration_seconds or 30)
    per_scene = project.per_scene_duration_seconds or 8
    rough_count = max(2, min(10, round(target / per_scene)))

    # Raw fallback in case Claude fails
    fallback = [{
        'title': f'Scene 1: {project.concept[:80]}',
        'prompt': project.concept,
        'duration_seconds': per_scene,
    }]

    if not getattr(settings, 'ANTHROPIC_API_KEY', ''):
        logger.warning('plan_scenes: ANTHROPIC_API_KEY not set, using fallback plan')
        return fallback

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

        theme_hint = ''
        if theme:
            theme_hint = (
                f'Overall style for the video: {theme.name} — {theme.description}. '
                f'Shot style: {theme.get_shot_style_display()}. '
                f'Music vibe: {theme.get_music_vibe_display()}.'
            )

        system = (
            "You are a video story planner for short-form AI video generation. "
            "Break a user's concept into a sequence of short scenes (each a separate AI-generated clip) "
            "that will be stitched together into one longer video. "
            "Write prompts optimized for Veo 3 / Runway Gen-4 / Kling: concrete, visual, specific — "
            "describe the shot, action, and setting. DO NOT write dialogue. DO NOT write cuts within a "
            "scene (each scene is one continuous shot). "
            "Output STRICT JSON only — an array of objects, no prose, no markdown fences."
        )

        user_msg = (
            f"Concept: {project.concept}\n"
            f"Subject: {subject.name}, a {subject.get_kind_display().lower()}"
            + (f" ({subject.get_species_display().lower()})" if subject.species else '')
            + f". Visual description: {subject.description or 'see prompts'}.\n"
            f"{theme_hint}\n"
            f"Target total duration: {target} seconds, split across approximately {rough_count} scenes. "
            f"Each scene is {per_scene} seconds.\n"
            + (f"Extra direction (applies to all scenes): {project.extra_detail}\n" if project.extra_detail else '')
            + f"\nReturn JSON like:\n"
              f'[\n'
              f'  {{"title": "Short scene label", "prompt": "Full visual description, 1-3 sentences", "duration_seconds": {per_scene}}},\n'
              f"  ...\n"
              f']\n'
              f'Each scene should flow visually to the next. Keep {subject.name} as the consistent character throughout.'
        )

        response = client.messages.create(
            model=DEFAULT_MODEL,
            max_tokens=3000,
            system=system,
            messages=[{'role': 'user', 'content': user_msg}],
        )

        raw = response.content[0].text.strip()
        # Claude sometimes wraps JSON in ```json ... ``` fences despite instructions
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```\s*$', '', raw)

        parsed = json.loads(raw)
        if not isinstance(parsed, list) or not parsed:
            raise ValueError(f'Planner returned non-list or empty: {raw[:200]}')

        # Sanitize each scene
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

        logger.info(f'Planned {len(scenes)} scenes for story {project.uuid}')
        return scenes

    except Exception as e:
        logger.exception(f'plan_scenes failed, using fallback: {e}')
        return fallback
