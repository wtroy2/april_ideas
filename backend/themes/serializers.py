from rest_framework import serializers
from .models import Theme, ShotStyle, MusicVibe


class ThemeSerializer(serializers.ModelSerializer):
    is_system = serializers.BooleanField(read_only=True)

    class Meta:
        model = Theme
        fields = [
            'id', 'uuid', 'organization', 'name', 'slug', 'description',
            'cover_emoji', 'shot_style', 'music_vibe',
            'prompt_template', 'caption_template',
            'default_scenarios', 'tags',
            'is_active', 'is_featured', 'is_system',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'uuid', 'organization', 'is_system', 'created_at', 'updated_at']


class CreateThemeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Theme
        fields = [
            'name', 'slug', 'description', 'cover_emoji',
            'shot_style', 'music_vibe',
            'prompt_template', 'caption_template',
            'default_scenarios', 'tags',
        ]

    def validate_shot_style(self, v):
        if v not in dict(ShotStyle.choices):
            raise serializers.ValidationError('Invalid shot style')
        return v

    def validate_music_vibe(self, v):
        if v not in dict(MusicVibe.choices):
            raise serializers.ValidationError('Invalid music vibe')
        return v
