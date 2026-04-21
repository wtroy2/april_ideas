from rest_framework import serializers
from .models import Subject, SubjectPhoto, SubjectKind, SubjectSpecies
from assets.serializers import AssetSerializer


class SubjectPhotoSerializer(serializers.ModelSerializer):
    asset = AssetSerializer(read_only=True)

    class Meta:
        model = SubjectPhoto
        fields = ['id', 'asset', 'order', 'is_primary', 'created_at']
        read_only_fields = ['id', 'created_at']


class SubjectSerializer(serializers.ModelSerializer):
    photos = SubjectPhotoSerializer(source='subject_photos', many=True, read_only=True)
    photo_count = serializers.SerializerMethodField()

    class Meta:
        model = Subject
        fields = [
            'id', 'uuid', 'name', 'kind', 'species',
            'auto_description', 'user_description', 'is_archived',
            'photos', 'photo_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'uuid', 'auto_description', 'created_at', 'updated_at']

    def get_photo_count(self, obj):
        return obj.subject_photos.count()


class CreateSubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ['name', 'kind', 'species', 'user_description']

    def validate_kind(self, v):
        if v not in dict(SubjectKind.choices):
            raise serializers.ValidationError('Invalid kind')
        return v
