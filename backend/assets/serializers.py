from rest_framework import serializers
from .models import Asset


class AssetSerializer(serializers.ModelSerializer):
    signed_url = serializers.SerializerMethodField()
    public_url = serializers.SerializerMethodField()

    class Meta:
        model = Asset
        fields = [
            'id', 'uuid', 'kind', 'status',
            'original_filename', 'content_type',
            'size_bytes', 'width', 'height', 'duration_seconds',
            'signed_url', 'public_url',
            'created_at', 'updated_at',
        ]
        read_only_fields = fields

    def get_signed_url(self, obj):
        if obj.status not in ('ready', 'scan_passed'):
            return None
        try:
            return obj.signed_url(expires_seconds=3600)
        except Exception:
            return None

    def get_public_url(self, obj):
        return obj.public_url()
