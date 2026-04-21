"""
Seed system themes on first migration. Idempotent — re-running is safe.

These are the starter pet-niche templates that ship with the product. Custom
themes built by orgs live in the same table with organization=<their org>.
"""

import logging

logger = logging.getLogger('themes')


SEED_THEMES = [
    {
        'slug': 'cat-asmr-cooking',
        'name': 'Cat ASMR Cooking',
        'cover_emoji': '🍳',
        'description': 'Hyper close-up of a cat preparing tiny food in a tiny kitchen. ASMR audio.',
        'shot_style': 'macro',
        'music_vibe': 'asmr_ambient',
        'prompt_template': (
            'Macro shot, soft warm lighting, {subject_description} preparing {scenario} in a tiny '
            'miniature kitchen. The {subject_name} is wearing a small chef hat. Hyper-realistic, '
            '8 second clip, ASMR style — focus on chopping, sizzling, and the cat\'s small paws. '
            '{detail}'
        ),
        'caption_template': (
            'Write a short, cozy Instagram caption for an ASMR cat-cooking video. The cat is '
            '{subject_name} ({subject_description}). Today\'s recipe: {scenario}. Use 1-2 emojis '
            'maximum. End with 5 niche hashtags.'
        ),
        'default_scenarios': [
            'tiny pancakes', 'a tiny burger', 'tiny ramen',
            'tiny pizza', 'a tiny fruit salad',
        ],
        'tags': ['cat', 'asmr', 'cooking', 'cozy'],
        'is_featured': True,
    },
    {
        'slug': 'pet-reacts-to',
        'name': 'Pet Reacts To...',
        'cover_emoji': '😼',
        'description': 'Classic reaction format — your pet sees something for the first time.',
        'shot_style': 'handheld',
        'music_vibe': 'trending',
        'prompt_template': (
            'Handheld iPhone-style video of {subject_description}. The {subject_name} encounters '
            '{scenario} for the first time and reacts. Authentic, slightly shaky, natural daylight. '
            '8 second clip. Capture the surprise. {detail}'
        ),
        'caption_template': (
            'Write a punchy, funny TikTok caption for a video of {subject_name} reacting to '
            '{scenario}. {subject_description}. One emoji. End with 4 trending pet hashtags.'
        ),
        'default_scenarios': [
            'a cucumber', 'a giant new toy', 'snow for the first time',
            'a robot vacuum', 'a mirror',
        ],
        'tags': ['cat', 'dog', 'reaction', 'viral', 'funny'],
        'is_featured': True,
    },
    {
        'slug': 'tiny-day-in-the-life',
        'name': 'Tiny Day in the Life',
        'cover_emoji': '☀️',
        'description': 'Wholesome lo-fi montage of your pet\'s daily routine — naps, snacks, zoomies.',
        'shot_style': 'cinematic',
        'music_vibe': 'lofi',
        'prompt_template': (
            'Cinematic, soft golden-hour lighting. A day in the life of {subject_description}. '
            'Scene: {scenario}. The {subject_name} is the focus, wholesome and serene. 8 second '
            'clip with shallow depth of field. {detail}'
        ),
        'caption_template': (
            'Write a wholesome, slightly poetic Instagram caption for a day-in-the-life video of '
            '{subject_name} ({subject_description}). Today: {scenario}. End with 3 cozy hashtags.'
        ),
        'default_scenarios': [
            'morning stretch by the window', 'snack time on the kitchen floor',
            'zoomies in the hallway', 'evening nap on the couch',
            'sunset stare out the back door',
        ],
        'tags': ['cat', 'dog', 'wholesome', 'lifestyle'],
        'is_featured': True,
    },
    {
        'slug': 'pet-in-costume',
        'name': 'Pet In Costume',
        'cover_emoji': '🎩',
        'description': 'Your pet, dressed up for a themed scene.',
        'shot_style': 'studio',
        'music_vibe': 'emotional',
        'prompt_template': (
            'Studio portrait lighting on a clean background. {subject_description} dressed as '
            '{scenario}. Confident pose. 8 second clip with subtle movement. {detail}'
        ),
        'caption_template': (
            'Write a short, fashion-magazine style caption for a portrait of {subject_name} '
            'dressed as {scenario}. {subject_description}. One emoji. 4 hashtags.'
        ),
        'default_scenarios': [
            'a tiny detective in a trench coat', 'a wizard in a starry robe',
            'a 1920s flapper', 'a chef', 'a tiny astronaut',
        ],
        'tags': ['cat', 'dog', 'fashion', 'costume'],
    },
    {
        'slug': 'pov-pet-adventure',
        'name': 'POV Pet Adventure',
        'cover_emoji': '🏔️',
        'description': 'POV from your pet\'s perspective on a tiny epic adventure.',
        'shot_style': 'pov',
        'music_vibe': 'emotional',
        'prompt_template': (
            'First-person POV from the perspective of {subject_description}. The {subject_name} '
            'is {scenario}. Cinematic, slightly low to the ground, dynamic motion. 8 second clip. '
            '{detail}'
        ),
        'caption_template': (
            'Write a dramatic-but-funny TikTok caption for a POV video of {subject_name} '
            '({subject_description}) {scenario}. Voice it like the pet is narrating their own '
            'adventure. End with 3 hashtags.'
        ),
        'default_scenarios': [
            'climbing Mount Couch', 'embarking on a hallway expedition',
            'discovering the great box', 'hunting the elusive red dot',
            'investigating the dishwasher',
        ],
        'tags': ['cat', 'dog', 'pov', 'adventure'],
    },
]


def seed_default_themes(sender, **kwargs):
    """Idempotent seeding of system themes."""
    from .models import Theme

    created_count = 0
    updated_count = 0

    for spec in SEED_THEMES:
        theme, created = Theme.objects.update_or_create(
            organization=None,
            slug=spec['slug'],
            defaults={
                'name': spec['name'],
                'cover_emoji': spec.get('cover_emoji', ''),
                'description': spec.get('description', ''),
                'shot_style': spec['shot_style'],
                'music_vibe': spec['music_vibe'],
                'prompt_template': spec['prompt_template'],
                'caption_template': spec.get('caption_template', ''),
                'default_scenarios': spec.get('default_scenarios', []),
                'tags': spec.get('tags', []),
                'is_active': True,
                'is_featured': spec.get('is_featured', False),
            },
        )
        if created:
            created_count += 1
        else:
            updated_count += 1

    if created_count or updated_count:
        logger.info(f'Themes seeded: {created_count} created, {updated_count} updated')
