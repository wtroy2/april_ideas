"""DRF serializers for the users app — focused, no lender-preference baggage."""

import re

from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .models import CustomUser, TwoFactorCode, UserSession


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['id', 'username', 'first_name', 'last_name', 'email', 'phone', 'avatar_url']


class RegisterSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['username', 'password', 'first_name', 'last_name', 'email', 'phone']
        extra_kwargs = {'password': {'write_only': True}}

    def validate_password(self, value):
        try:
            validate_password(value)
        except ValidationError as e:
            raise serializers.ValidationError(e.messages)
        return value

    def create(self, validated_data):
        return CustomUser.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            phone=validated_data.get('phone', ''),
        )


class LoginInitiateSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150, help_text='Username or email')
    password = serializers.CharField(write_only=True)

    def validate_username(self, value):
        return value.strip().lower()


class LoginVerifySerializer(serializers.Serializer):
    login_session_id = serializers.CharField()
    verification_code = serializers.CharField(min_length=4, max_length=10)

    def validate_verification_code(self, value):
        return value.strip().upper()


class ResendCodeSerializer(serializers.Serializer):
    login_session_id = serializers.CharField()


class ForgotUsernameSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        return value.strip().lower()


class ForgotPasswordInitiateSerializer(serializers.Serializer):
    username_or_email = serializers.CharField(max_length=150)

    def validate_username_or_email(self, value):
        return value.strip().lower()


class PasswordResetVerifySerializer(serializers.Serializer):
    reset_session_id = serializers.CharField()
    verification_code = serializers.CharField(min_length=6, max_length=10)
    new_password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    def validate_verification_code(self, value):
        return value.strip().upper()

    def validate_new_password(self, value):
        try:
            validate_password(value)
        except ValidationError as e:
            raise serializers.ValidationError(e.messages)
        return value

    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({'confirm_password': 'Passwords do not match.'})
        return attrs


class ResendPasswordResetSerializer(serializers.Serializer):
    reset_session_id = serializers.CharField()


class UserSessionSerializer(serializers.ModelSerializer):
    user_agent_short = serializers.SerializerMethodField()
    is_current_session = serializers.SerializerMethodField()

    class Meta:
        model = UserSession
        fields = [
            'id', 'session_key', 'ip_address', 'user_agent_short',
            'created_at', 'last_activity', 'is_active',
            'country', 'city', 'is_current_session',
        ]
        read_only_fields = ['session_key', 'created_at', 'last_activity']

    def get_user_agent_short(self, obj):
        ua = (obj.user_agent or '').lower()
        browser = (
            'Chrome' if 'chrome' in ua and 'edg' not in ua else
            'Edge' if 'edg' in ua else
            'Firefox' if 'firefox' in ua else
            'Safari' if 'safari' in ua else 'Unknown'
        )
        os_name = (
            'macOS' if 'mac' in ua else
            'Windows' if 'windows' in ua else
            'iOS' if 'iphone' in ua or 'ipad' in ua else
            'Android' if 'android' in ua else
            'Linux' if 'linux' in ua else 'Unknown'
        )
        return f'{browser} on {os_name}'

    def get_is_current_session(self, obj):
        request = self.context.get('request')
        if not request or not hasattr(request, 'auth'):
            return False
        if hasattr(request.auth, 'get'):
            return str(request.auth.get('jti', '')) == obj.session_key
        return False
