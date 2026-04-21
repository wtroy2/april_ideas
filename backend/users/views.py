"""
Auth views for Critter.

Function-based DRF views (per RateRail philosophy). Implements the full
2FA login flow: initiate -> verify -> issue JWT, plus password reset and
username recovery.
"""

import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from django.db.models import Q

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from .models import CustomUser, TwoFactorCode, UserSession
from .serializers import (
    UserSerializer, RegisterSerializer,
    LoginInitiateSerializer, LoginVerifySerializer, ResendCodeSerializer,
    ForgotUsernameSerializer, ForgotPasswordInitiateSerializer,
    PasswordResetVerifySerializer, ResendPasswordResetSerializer,
    UserSessionSerializer,
)

logger = logging.getLogger('auth_debug')


# --------------------------------------------------------------------------
# Registration + basic profile
# --------------------------------------------------------------------------

@api_view(['POST'])
@permission_classes([AllowAny])
def register(request):
    serializer = RegisterSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    user = serializer.save()
    return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_username(request):
    return Response({
        'username': request.user.username,
        'user_firstname': request.user.first_name,
        'user_email': request.user.email,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_info(request):
    return Response(UserSerializer(request.user).data)


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def update_user_info(request):
    serializer = UserSerializer(request.user, data=request.data, partial=True)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    serializer.save()
    return Response(serializer.data)


# --------------------------------------------------------------------------
# Two-factor login flow
# --------------------------------------------------------------------------

@api_view(['POST'])
@permission_classes([AllowAny])
def initiate_login(request):
    """
    Step 1: validate username + password.
      - If REQUIRE_2FA is True: send a 2FA code via email, return a session id
        the client uses in step 2.
      - If REQUIRE_2FA is False: issue JWT immediately (single-step login).
    """
    from django.conf import settings

    serializer = LoginInitiateSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    username_or_email = serializer.validated_data['username']
    password = serializer.validated_data['password']

    try:
        user = CustomUser.objects.get(Q(username__iexact=username_or_email) | Q(email__iexact=username_or_email))
    except CustomUser.DoesNotExist:
        return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)

    auth_user = authenticate(username=user.username, password=password)
    if not auth_user:
        logger.info(f'Failed password for {user.username}')
        return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)

    # 2FA disabled — issue JWT immediately (frontend detects 'access' in payload
    # and skips the verify-code step).
    if not getattr(settings, 'REQUIRE_2FA', True):
        refresh = RefreshToken.for_user(user)
        access = refresh.access_token
        UserSession.create_for_user(user, request, str(access['jti']))
        return Response({
            'access': str(access),
            'refresh': str(refresh),
            'user': UserSerializer(user).data,
            'two_factor_skipped': True,
        })

    # Standard 2FA path
    login_session_id = secrets.token_urlsafe(32)
    try:
        user.send_2fa_code(request, login_session_id)
    except ValueError as e:
        return Response({'error': str(e)}, status=status.HTTP_429_TOO_MANY_REQUESTS)

    return Response({
        'login_session_id': login_session_id,
        'message': 'Verification code sent to your email',
        'email_hint': _mask_email(user.email),
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def verify_login(request):
    """Step 2: user submits 2FA code + login_session_id; we issue JWT."""
    serializer = LoginVerifySerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    session_id = serializer.validated_data['login_session_id']
    code = serializer.validated_data['verification_code']

    try:
        code_instance = TwoFactorCode.objects.select_related('user').get(
            session_id=session_id,
            code_type='login',
            is_used=False,
            expires_at__gt=timezone.now(),
        )
    except TwoFactorCode.DoesNotExist:
        return Response({'error': 'No valid verification code found'}, status=status.HTTP_400_BAD_REQUEST)

    user = code_instance.user
    ok, message = code_instance.verify_code(code)
    if not ok:
        return Response({'error': message}, status=status.HTTP_400_BAD_REQUEST)

    refresh = RefreshToken.for_user(user)
    access = refresh.access_token
    UserSession.create_for_user(user, request, str(access['jti']))

    return Response({
        'access': str(access),
        'refresh': str(refresh),
        'user': UserSerializer(user).data,
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def resend_verification_code(request):
    serializer = ResendCodeSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    session_id = serializer.validated_data['login_session_id']

    last = TwoFactorCode.objects.filter(
        session_id=session_id, code_type='login'
    ).order_by('-created_at').first()

    if not last:
        return Response({'error': 'No login session found'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        last.user.send_2fa_code(request, session_id)
    except ValueError as e:
        return Response({'error': str(e)}, status=status.HTTP_429_TOO_MANY_REQUESTS)

    return Response({'message': 'New verification code sent'})


# --------------------------------------------------------------------------
# Password reset
# --------------------------------------------------------------------------

@api_view(['POST'])
@permission_classes([AllowAny])
def initiate_password_reset(request):
    serializer = ForgotPasswordInitiateSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    val = serializer.validated_data['username_or_email']

    user = CustomUser.objects.filter(Q(username__iexact=val) | Q(email__iexact=val)).first()
    # Don't leak account existence — return success either way
    if not user:
        return Response({'message': 'If an account exists, a reset code has been sent.'})

    reset_session_id = secrets.token_urlsafe(32)
    try:
        user.send_password_reset_code(request, reset_session_id)
    except ValueError:
        pass

    return Response({
        'reset_session_id': reset_session_id,
        'message': 'If an account exists, a reset code has been sent.',
        'email_hint': _mask_email(user.email),
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def verify_password_reset(request):
    serializer = PasswordResetVerifySerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    session_id = serializer.validated_data['reset_session_id']
    code = serializer.validated_data['verification_code']
    new_pwd_hash = make_password(serializer.validated_data['new_password'])

    try:
        code_instance = TwoFactorCode.objects.select_related('user').get(
            session_id=session_id,
            code_type='password_reset',
            is_used=False,
            expires_at__gt=timezone.now(),
        )
    except TwoFactorCode.DoesNotExist:
        return Response({'error': 'No valid reset code found'}, status=status.HTTP_400_BAD_REQUEST)

    ok, message = code_instance.verify_code(code, new_password_hash=new_pwd_hash)
    if not ok:
        return Response({'error': message}, status=status.HTTP_400_BAD_REQUEST)

    code_instance.complete_password_reset()
    return Response({'message': 'Password reset successful — you can now sign in.'})


@api_view(['POST'])
@permission_classes([AllowAny])
def resend_password_reset_code(request):
    serializer = ResendPasswordResetSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    session_id = serializer.validated_data['reset_session_id']
    last = TwoFactorCode.objects.filter(
        session_id=session_id, code_type='password_reset'
    ).order_by('-created_at').first()
    if not last:
        return Response({'error': 'No reset session found'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        last.user.send_password_reset_code(request, session_id)
    except ValueError as e:
        return Response({'error': str(e)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
    return Response({'message': 'New reset code sent'})


# --------------------------------------------------------------------------
# Forgot username
# --------------------------------------------------------------------------

@api_view(['POST'])
@permission_classes([AllowAny])
def forgot_username(request):
    serializer = ForgotUsernameSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    email = serializer.validated_data['email']
    user = CustomUser.objects.filter(email__iexact=email).first()
    if user:
        try:
            user.send_username_recovery(request)
        except ValueError:
            pass
    # Don't leak whether the email exists
    return Response({'message': 'If an account exists, your username has been sent.'})


# --------------------------------------------------------------------------
# Sessions
# --------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user_sessions(request):
    sessions = UserSession.objects.filter(user=request.user, is_active=True)
    return Response(UserSessionSerializer(sessions, many=True, context={'request': request}).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def terminate_session(request, session_id):
    try:
        s = UserSession.objects.get(id=session_id, user=request.user)
    except UserSession.DoesNotExist:
        return Response({'error': 'Session not found'}, status=status.HTTP_404_NOT_FOUND)
    s.terminate()
    return Response({'message': 'Session terminated'})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def enhanced_logout(request):
    """
    Logout: terminate the current session and blacklist the refresh token if provided.
    """
    refresh_token = request.data.get('refresh')
    if refresh_token:
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except Exception as e:
            logger.warning(f'Failed to blacklist refresh token: {e}')

    # Find current session by JWT jti and deactivate
    if hasattr(request.auth, 'get'):
        jti = str(request.auth.get('jti', ''))
        UserSession.objects.filter(user=request.user, session_key=jti).update(is_active=False)

    return Response({'message': 'Logged out'})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def validate_session_enhanced(request):
    return Response({'valid': True, 'user': UserSerializer(request.user).data})


# --------------------------------------------------------------------------
# Token refresh override (so frontend can hit /api/users/token/refresh/ uniformly)
# --------------------------------------------------------------------------

class EnhancedTokenRefreshView(TokenRefreshView):
    """Standard simplejwt TokenRefreshView — wrapped for symmetry with RateRail."""
    pass


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _mask_email(email):
    """Return a masked hint like 'a***@example.com'."""
    if not email or '@' not in email:
        return ''
    local, domain = email.split('@', 1)
    if len(local) <= 1:
        return f'{local}***@{domain}'
    return f'{local[0]}***@{domain}'
