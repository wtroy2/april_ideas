from rest_framework import serializers

from assets.serializers import AssetSerializer
from generations.serializers import GenerationSerializer
from .models import StoryProject, StoryScene, StoryStatus, TransitionKind


class StorySceneSerializer(serializers.ModelSerializer):
    takes = GenerationSerializer(source='generations', many=True, read_only=True)
    chosen_generation_uuid = serializers.UUIDField(
        source='chosen_generation.uuid', read_only=True, allow_null=True,
    )

    class Meta:
        model = StoryScene
        fields = [
            'id', 'order', 'title', 'prompt', 'duration_seconds',
            'desired_takes', 'transition_out',
            'chosen_generation', 'chosen_generation_uuid',
            'takes', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'takes', 'chosen_generation_uuid', 'created_at', 'updated_at']


class StoryProjectSerializer(serializers.ModelSerializer):
    scenes = StorySceneSerializer(many=True, read_only=True)
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    theme_name = serializers.CharField(source='theme.name', read_only=True, allow_null=True)
    music_track_name = serializers.CharField(
        source='music_track.original_filename', read_only=True, allow_null=True,
    )
    final_video_asset = AssetSerializer(read_only=True)
    total_duration_seconds = serializers.SerializerMethodField()

    class Meta:
        model = StoryProject
        fields = [
            'id', 'uuid',
            'subject', 'subject_name',
            'theme', 'theme_name',
            'title', 'concept',
            'provider', 'aspect_ratio',
            'target_duration_seconds', 'per_scene_duration_seconds',
            'extra_detail', 'expand_prompts_with_claude', 'generate_captions',
            'use_photo_background', 'person_generation',
            # Audio mix
            'original_audio_volume', 'original_audio_fade_in_seconds', 'original_audio_fade_out_seconds',
            'music_track', 'music_track_name',
            'music_volume', 'music_start_offset_seconds',
            'music_fade_in_seconds', 'music_fade_out_seconds',
            # State
            'status', 'error_message',
            'final_video_asset', 'total_duration_seconds',
            'scenes',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'uuid', 'status', 'error_message', 'final_video_asset',
            'subject_name', 'theme_name', 'music_track_name',
            'total_duration_seconds', 'scenes', 'created_at', 'updated_at',
        ]

    def get_total_duration_seconds(self, obj):
        return sum(s.duration_seconds for s in obj.scenes.all())


class CreateStorySerializer(serializers.Serializer):
    """Input for POST /api/stories/ — creates the project then kicks off planning."""
    subject_uuid = serializers.UUIDField()
    theme_uuid = serializers.UUIDField(required=False, allow_null=True)
    title = serializers.CharField(max_length=200, required=False, allow_blank=True, default='')
    concept = serializers.CharField()
    target_duration_seconds = serializers.IntegerField(min_value=8, max_value=180, default=30)
    per_scene_duration_seconds = serializers.ChoiceField(choices=[4, 6, 8], default=8)
    provider = serializers.CharField(default='veo_31_lite')
    aspect_ratio = serializers.ChoiceField(choices=['9:16', '16:9', '1:1'], default='9:16')
    extra_detail = serializers.CharField(required=False, allow_blank=True, default='')
    expand_prompts_with_claude = serializers.BooleanField(default=True)
    use_photo_background = serializers.BooleanField(default=True)
    person_generation = serializers.ChoiceField(
        choices=['allow_adult', 'dont_allow', 'allow_all'], default='allow_adult',
    )
