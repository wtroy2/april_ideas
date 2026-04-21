from rest_framework import serializers

from assets.serializers import AssetSerializer
from .models import GenerationBatch, Generation, VideoProvider as VP


class GenerationSerializer(serializers.ModelSerializer):
    video_asset = AssetSerializer(read_only=True)
    video_asset_raw = AssetSerializer(read_only=True)

    class Meta:
        model = Generation
        fields = [
            'id', 'uuid', 'batch', 'scenario', 'take_index', 'detail',
            'rendered_prompt', 'video_asset', 'video_asset_raw', 'caption',
            'status', 'started_at', 'finished_at', 'error_message',
            'created_at', 'updated_at',
        ]
        read_only_fields = fields


class GenerationBatchSerializer(serializers.ModelSerializer):
    generations = GenerationSerializer(many=True, read_only=True)
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    theme_name = serializers.CharField(source='theme.name', read_only=True)
    music_track_uuid = serializers.UUIDField(source='music_track.uuid', read_only=True, allow_null=True)
    music_track_name = serializers.CharField(source='music_track.original_filename', read_only=True, allow_null=True)
    succeeded_count = serializers.SerializerMethodField()
    failed_count = serializers.SerializerMethodField()
    total_count = serializers.SerializerMethodField()

    class Meta:
        model = GenerationBatch
        fields = [
            'id', 'uuid', 'organization', 'subject', 'subject_name',
            'theme', 'theme_name', 'provider', 'aspect_ratio', 'duration_seconds',
            'extra_detail', 'expand_prompts_with_claude', 'generate_captions',
            'use_photo_background', 'person_generation',
            'variations_per_scenario',
            # Audio mix
            'original_audio_volume', 'original_audio_fade_in_seconds', 'original_audio_fade_out_seconds',
            'music_track', 'music_track_uuid', 'music_track_name',
            'music_volume', 'music_start_offset_seconds',
            'music_fade_in_seconds', 'music_fade_out_seconds',
            'status', 'notes',
            'succeeded_count', 'failed_count', 'total_count',
            'generations', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'uuid', 'organization', 'status', 'created_at', 'updated_at']

    def get_succeeded_count(self, obj):
        return obj.generations.filter(status='succeeded').count()

    def get_failed_count(self, obj):
        return obj.generations.filter(status='failed').count()

    def get_total_count(self, obj):
        return obj.generations.count()


class CreateBatchSerializer(serializers.Serializer):
    """
    Input contract for kicking off a batch.

    Required: subject_uuid, theme_uuid, scenarios (list of strings, one per video)
    Optional: provider, aspect_ratio, duration_seconds, extra_detail,
              expand_prompts_with_claude, generate_captions, notes
    """
    subject_uuid = serializers.UUIDField()
    theme_uuid = serializers.UUIDField()
    scenarios = serializers.ListField(
        child=serializers.CharField(max_length=500), allow_empty=False, max_length=20,
        help_text='One scenario per video to generate. Each becomes a child Generation.',
    )
    provider = serializers.ChoiceField(choices=VP.choices, default=VP.VEO_31_LITE)
    aspect_ratio = serializers.ChoiceField(choices=['9:16', '16:9', '1:1'], default='9:16')
    # Veo only supports 4, 6, or 8 seconds today.
    duration_seconds = serializers.ChoiceField(choices=[4, 6, 8], default=8)
    extra_detail = serializers.CharField(required=False, allow_blank=True, default='')
    expand_prompts_with_claude = serializers.BooleanField(default=True)
    generate_captions = serializers.BooleanField(default=True)
    use_photo_background = serializers.BooleanField(default=True)
    person_generation = serializers.ChoiceField(
        choices=['allow_adult', 'dont_allow', 'allow_all'],
        default='allow_adult',
    )
    variations_per_scenario = serializers.IntegerField(min_value=1, max_value=5, default=1)
    notes = serializers.CharField(required=False, allow_blank=True, default='')


class UpdateBatchAudioSerializer(serializers.Serializer):
    """PATCH /batches/:uuid/audio/ — user is tweaking the audio mix settings.
    Does NOT bake an MP4 — call /remix/ for that. Validates + saves the draft."""
    original_audio_volume = serializers.FloatField(required=False, min_value=0.0, max_value=2.0)
    original_audio_fade_in_seconds = serializers.FloatField(required=False, min_value=0.0, max_value=10.0)
    original_audio_fade_out_seconds = serializers.FloatField(required=False, min_value=0.0, max_value=10.0)
    music_track_uuid = serializers.UUIDField(required=False, allow_null=True)
    music_volume = serializers.FloatField(required=False, min_value=0.0, max_value=2.0)
    music_start_offset_seconds = serializers.FloatField(required=False, min_value=0.0, max_value=3600.0)
    music_fade_in_seconds = serializers.FloatField(required=False, min_value=0.0, max_value=10.0)
    music_fade_out_seconds = serializers.FloatField(required=False, min_value=0.0, max_value=10.0)


class AudioMixSerializer(serializers.ModelSerializer):
    output_asset_url = serializers.SerializerMethodField()
    music_track_name = serializers.CharField(source='music_track.original_filename', read_only=True, allow_null=True)

    class Meta:
        from .models import AudioMix
        model = AudioMix
        fields = [
            'id', 'uuid',
            'original_audio_volume', 'original_audio_fade_in_seconds', 'original_audio_fade_out_seconds',
            'music_track', 'music_track_name',
            'music_volume', 'music_start_offset_seconds',
            'music_fade_in_seconds', 'music_fade_out_seconds',
            'status', 'error_message',
            'output_asset_url', 'created_at',
        ]
        read_only_fields = fields

    def get_output_asset_url(self, obj):
        if not obj.output_asset:
            return None
        try:
            return obj.output_asset.signed_url(expires_seconds=3600)
        except Exception:
            return None
