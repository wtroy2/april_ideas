"""
Auth middleware for Critter — lifted from RateRail with the same three pieces:

  1. SingleDeviceSessionMiddleware — verifies the request's JWT jti matches
     an active UserSession row, with device-fingerprint check.
  2. TwoFactorSecurityMiddleware — adds security headers + auth logging.
  3. AuthenticationErrorMiddleware — converts auth exceptions into clean 401s.
"""

import logging

from django.utils.deprecation import MiddlewareMixin
from django.http import JsonResponse
from django.conf import settings
from django.utils import timezone

from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, AuthenticationFailed

from .models import UserSession

logger = logging.getLogger('auth_debug')


class SingleDeviceSessionMiddleware(MiddlewareMixin):
    """Enforce one active session per device for users with valid JWTs."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.jwt_auth = JWTAuthentication()
        super().__init__(get_response)

    def process_request(self, request):
        if self._should_skip(request):
            return None

        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if not auth_header.startswith('Bearer '):
            return None

        try:
            validated_token = self.jwt_auth.get_validated_token(auth_header[7:])
            user = self.jwt_auth.get_user(validated_token)

            if not user or not user.is_authenticated:
                return None

            if not getattr(settings, 'SINGLE_DEVICE_SESSION', True):
                return None

            session_key = str(validated_token.get('jti', ''))
            if not session_key:
                return self._error('Invalid session')

            try:
                user_session = UserSession.objects.get(
                    user=user, session_key=session_key, is_active=True
                )
            except UserSession.DoesNotExist:
                logger.warning(f'Session not found for {user.username}')
                return self._error('Session not found')

            current_fp = UserSession.create_device_fingerprint(request)
            if current_fp != user_session.device_fingerprint:
                logger.warning(f'Device fingerprint mismatch for {user.username}')
                user_session.terminate()
                return self._error('Device verification failed')

            # Throttle activity updates to once per 5 minutes
            now = timezone.now()
            if (now - user_session.last_activity).total_seconds() > 300:
                user_session.last_activity = now
                user_session.save(update_fields=['last_activity'])

        except InvalidToken:
            return None
        except Exception as e:
            logger.error(f'Session middleware error: {e}')
            return None

        return None

    def _should_skip(self, request):
        path = request.path_info

        # Auth endpoints (login, refresh, register, password reset, etc.)
        skip_suffixes = [
            '/auth/initiate-login/', '/auth/verify-login/', '/auth/resend-code/',
            '/auth/forgot-username/', '/auth/forgot-password/',
            '/auth/verify-password-reset/', '/auth/resend-password-reset/',
            '/token/', '/token/refresh/', '/register/',
        ]
        for suffix in skip_suffixes:
            if path.endswith(suffix):
                return True

        # Admin and static
        if path.startswith('/admin/') or path.startswith('/static/'):
            return True
        # Health and root
        if path.startswith('/health/') or path == '/':
            return True
        # django-rq dashboard (its own auth)
        if path.startswith('/django-rq/'):
            return True

        return False

    def _error(self, message):
        return JsonResponse({
            'error': message,
            'code': 'session_invalid',
            'action_required': 'reauthenticate',
        }, status=401)


class TwoFactorSecurityMiddleware(MiddlewareMixin):
    """Adds security headers + lightweight access logging on auth endpoints."""

    def process_request(self, request):
        path = request.path_info
        if any(p in path for p in ['/auth/', '/token/']):
            ip = self._get_ip(request)
            ua = request.META.get('HTTP_USER_AGENT', '')[:100]
            logger.info(f'Auth endpoint access: {path} from {ip} - {ua}')
        return None

    def process_response(self, request, response):
        path = request.path_info
        if any(p in path for p in ['/auth/', '/token/']):
            response['X-Content-Type-Options'] = 'nosniff'
            response['X-Frame-Options'] = 'DENY'
            response['X-XSS-Protection'] = '1; mode=block'
            response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
            response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
        return response

    def _get_ip(self, request):
        x = request.META.get('HTTP_X_FORWARDED_FOR')
        if x:
            return x.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '')


class AuthenticationErrorMiddleware(MiddlewareMixin):
    """Converts authentication exceptions to clean 401 JSON responses."""

    def process_exception(self, request, exception):
        if isinstance(exception, (InvalidToken, AuthenticationFailed)):
            return JsonResponse({
                'error': str(exception),
                'code': 'authentication_failed',
                'action_required': 'reauthenticate',
            }, status=401)
        return None
