from rest_framework import serializers
from .models import Organization, OrganizationMember, OrganizationInvitation, MemberRole


class OrganizationSerializer(serializers.ModelSerializer):
    member_count = serializers.SerializerMethodField()
    your_role = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = [
            'id', 'name', 'org_type', 'description', 'website',
            'contact_email', 'created_at', 'member_count', 'your_role',
        ]
        read_only_fields = ['id', 'created_at']

    def get_member_count(self, obj):
        return obj.get_member_count()

    def get_your_role(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            try:
                return obj.members.get(user=request.user).role
            except OrganizationMember.DoesNotExist:
                return None
        return None


class CreateOrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ['name', 'org_type', 'description', 'website', 'contact_email']


class OrganizationMemberSerializer(serializers.ModelSerializer):
    user_username = serializers.CharField(source='user.username', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)
    user_first_name = serializers.CharField(source='user.first_name', read_only=True)
    user_last_name = serializers.CharField(source='user.last_name', read_only=True)

    class Meta:
        model = OrganizationMember
        fields = ['id', 'user', 'user_username', 'user_email',
                  'user_first_name', 'user_last_name', 'role', 'joined_at']
        read_only_fields = ['id', 'joined_at']


class OrganizationInvitationSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    inviter_name = serializers.SerializerMethodField()

    class Meta:
        model = OrganizationInvitation
        fields = ['id', 'organization', 'organization_name', 'email', 'token',
                  'role', 'created_at', 'expires_at', 'is_used',
                  'email_sent', 'inviter_name']
        read_only_fields = ['id', 'token', 'created_at', 'is_used', 'email_sent']

    def get_inviter_name(self, obj):
        u = obj.created_by
        return f'{u.first_name} {u.last_name}'.strip() or u.username


class CreateInvitationSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=MemberRole.choices, default=MemberRole.VIEWER)
