"""
User models for Critter.

Lifted and simplified from RateRail (`backend/users/models.py`):
  - CustomUser: AbstractUser with unique email + a few profile fields
  - TwoFactorCode: handles login 2FA + password reset + username recovery
  - UserSession: tracks active sessions for single-device enforcement

Removed lender-specific stuff (UserLenderPreference, notification prefs with
loan-specific toggles) since this is a creator-facing app.
"""

import secrets
import string
import hashlib
import logging
from datetime import timedelta

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.base_user import BaseUserManager
from django.utils import timezone
from django.conf import settings
from django.db.models import Q

logger = logging.getLogger('auth_debug')


class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)


class CustomUser(AbstractUser):
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=15, blank=True, null=True)
    avatar_url = models.URLField(blank=True, null=True)

    def __str__(self):
        return self.username

    def send_2fa_code(self, request, login_session_id):
        return TwoFactorCode.create_for_user(self, request, login_session_id, 'login')

    def send_password_reset_code(self, request, reset_session_id):
        return TwoFactorCode.create_for_user(self, request, reset_session_id, 'password_reset')

    def send_username_recovery(self, request):
        session_id = f'username_recovery_{timezone.now().timestamp()}'
        return TwoFactorCode.create_for_user(self, request, session_id, 'username_recovery')

    def verify_2fa_code(self, code, login_session_id):
        try:
            code_instance = self.two_factor_codes.get(
                session_id=login_session_id,
                code_type='login',
                is_used=False,
                expires_at__gt=timezone.now(),
            )
            return code_instance.verify_code(code)
        except TwoFactorCode.DoesNotExist:
            logger.warning(f'No valid 2FA code found for user {self.username} session {login_session_id}')
            return False, 'No valid verification code found'

    def verify_password_reset_code(self, code, reset_session_id, new_password_hash):
        try:
            code_instance = self.two_factor_codes.get(
                session_id=reset_session_id,
                code_type='password_reset',
                is_used=False,
                expires_at__gt=timezone.now(),
            )
            return code_instance.verify_code(code, new_password_hash=new_password_hash)
        except TwoFactorCode.DoesNotExist:
            logger.warning(f'No valid password reset code found for user {self.username}')
            return False, 'No valid password reset code found'

    def complete_password_reset(self, reset_session_id):
        try:
            code_instance = self.two_factor_codes.get(
                session_id=reset_session_id,
                code_type='password_reset',
                is_used=True,
            )
            return code_instance.complete_password_reset()
        except TwoFactorCode.DoesNotExist:
            return False


class TwoFactorCode(models.Model):
    """
    Stores email-delivered codes for login 2FA, password reset, and username
    recovery. Codes are hashed at rest (SHA256), with the raw code held only
    in memory long enough to send the email.
    """

    CODE_TYPE_CHOICES = [
        ('login', 'Login Verification'),
        ('password_reset', 'Password Reset'),
        ('username_recovery', 'Username Recovery'),
    ]

    user = models.ForeignKey('CustomUser', on_delete=models.CASCADE, related_name='two_factor_codes')
    code = models.CharField(max_length=64)  # SHA256 hex
    raw_code = None  # transient, holds raw code between create() and send_email()
    code_type = models.CharField(max_length=20, choices=CODE_TYPE_CHOICES, default='login')
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    used_at = models.DateTimeField(null=True, blank=True)
    attempts = models.IntegerField(default=0)
    max_attempts = models.IntegerField(default=3)

    session_id = models.CharField(max_length=100)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField()

    new_password_hash = models.CharField(max_length=128, null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', 'code_type', 'is_used', 'expires_at']),
            models.Index(fields=['session_id', 'code_type']),
            models.Index(fields=['created_at']),
        ]
        ordering = ['-created_at']
        unique_together = [('session_id', 'code_type')]

    def __str__(self):
        return f'{self.get_code_type_display()} code for {self.user.username} - {self.created_at}'

    def save(self, *args, **kwargs):
        if not self.expires_at:
            if self.code_type == 'password_reset':
                expiry = getattr(settings, 'PASSWORD_RESET_CODE_EXPIRY_MINUTES', 30)
            else:
                expiry = getattr(settings, 'TWO_FACTOR_CODE_EXPIRY_MINUTES', 10)
            self.expires_at = timezone.now() + timedelta(minutes=expiry)
        super().save(*args, **kwargs)

    @classmethod
    def generate_code(cls, code_type='login'):
        if code_type == 'password_reset':
            length = getattr(settings, 'PASSWORD_RESET_CODE_LENGTH', 8)
        else:
            length = getattr(settings, 'TWO_FACTOR_CODE_LENGTH', 6)
        return ''.join(secrets.choice(string.digits) for _ in range(length))

    @staticmethod
    def get_client_ip(request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '')

    @classmethod
    def create_for_user(cls, user, request, session_id, code_type='login', **extra_data):
        # Daily limit
        today = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        daily_count = cls.objects.filter(
            user=user, code_type=code_type, created_at__gte=today
        ).count()

        if code_type == 'password_reset':
            max_daily = getattr(settings, 'MAX_DAILY_PASSWORD_RESET_CODES', 5)
        elif code_type == 'username_recovery':
            max_daily = getattr(settings, 'MAX_DAILY_USERNAME_RECOVERY_REQUESTS', 3)
        else:
            max_daily = getattr(settings, 'MAX_DAILY_2FA_CODES', 10)

        if daily_count >= max_daily:
            logger.warning(f'User {user.username} hit daily {code_type} limit ({daily_count}/{max_daily})')
            raise ValueError(f'Daily limit of {max_daily} {code_type} codes exceeded')

        # Invalidate prior codes for same session+type
        cls.objects.filter(
            user=user, code_type=code_type, session_id=session_id,
            is_used=False, expires_at__gt=timezone.now(),
        ).update(is_used=True, used_at=timezone.now())

        raw_code = cls.generate_code(code_type)
        hashed = hashlib.sha256(raw_code.encode()).hexdigest()

        code_instance = cls.objects.create(
            user=user,
            code=hashed,
            code_type=code_type,
            session_id=session_id,
            ip_address=cls.get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
            **extra_data,
        )
        code_instance.raw_code = raw_code

        if not code_instance.send_email():
            code_instance.delete()
            raise ValueError(f'Failed to send {code_type} email')

        logger.info(f'{code_type} code sent to {user.email} for session {session_id}')
        return code_instance

    def verify_code(self, provided_code, **extra):
        if self.is_used:
            return False, 'Code has already been used'
        if timezone.now() > self.expires_at:
            return False, 'Code has expired'
        if self.attempts >= self.max_attempts:
            return False, 'Maximum attempts exceeded'

        self.attempts += 1
        if self.code_type == 'password_reset' and 'new_password_hash' in extra:
            self.new_password_hash = extra['new_password_hash']
        self.save()

        provided_hash = hashlib.sha256(provided_code.encode()).hexdigest()
        if provided_hash == self.code:
            self.is_used = True
            self.used_at = timezone.now()
            self.save()
            logger.info(f'{self.code_type} code verified for {self.user.username}')
            return True, 'Code verified successfully'

        logger.warning(f'Invalid {self.code_type} code for {self.user.username} ({self.attempts}/{self.max_attempts})')
        return False, f'Invalid code ({self.attempts}/{self.max_attempts} attempts)'

    def send_email(self):
        """Send the code via email. Lean implementation — no fancy HTML templates yet."""
        if not self.raw_code:
            return False
        try:
            from django.core.mail import send_mail
            subject_map = {
                'login': 'Your Critter login code',
                'password_reset': 'Reset your Critter password',
                'username_recovery': 'Your Critter username',
            }
            subject = subject_map.get(self.code_type, 'Your Critter code')

            if self.code_type == 'username_recovery':
                body = (
                    f'Hi {self.user.first_name or "there"},\n\n'
                    f'You requested your Critter username.\n'
                    f'Your username is: {self.user.username}\n\n'
                    f'Sign in: {settings.SITE_URL}/login\n\n'
                    f'— Critter'
                )
            elif self.code_type == 'password_reset':
                expiry = getattr(settings, 'PASSWORD_RESET_CODE_EXPIRY_MINUTES', 30)
                body = (
                    f'Hi {self.user.first_name or "there"},\n\n'
                    f'Your Critter password reset code is: {self.raw_code}\n'
                    f'This code expires in {expiry} minutes.\n\n'
                    f'If you didn\'t request this, you can safely ignore this email.\n\n'
                    f'— Critter'
                )
            else:
                expiry = getattr(settings, 'TWO_FACTOR_CODE_EXPIRY_MINUTES', 10)
                body = (
                    f'Hi {self.user.first_name or "there"},\n\n'
                    f'Your Critter login code is: {self.raw_code}\n'
                    f'This code expires in {expiry} minutes.\n\n'
                    f'If you didn\'t try to sign in, you can ignore this email.\n\n'
                    f'— Critter'
                )

            send_mail(
                subject=subject,
                message=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[self.user.email],
                fail_silently=False,
            )
            return True
        except Exception as e:
            logger.error(f'Failed to send {self.code_type} email to {self.user.email}: {e}')
            return False

    def complete_password_reset(self):
        if self.code_type != 'password_reset':
            raise ValueError('Code is not a password reset code')
        if not self.is_used:
            raise ValueError('Code must be verified before completing reset')
        if not self.new_password_hash:
            raise ValueError('No new password provided')

        self.user.password = self.new_password_hash
        self.user.save()

        # Kill all active sessions for safety
        UserSession.objects.filter(user=self.user, is_active=True).update(is_active=False)

        # Invalidate other unused codes for this user
        TwoFactorCode.objects.filter(
            user=self.user, is_used=False, expires_at__gt=timezone.now()
        ).exclude(id=self.id).update(is_used=True, used_at=timezone.now())

        logger.info(f'Password reset completed for {self.user.username}')
        return True

    @classmethod
    def cleanup_expired(cls):
        deleted = cls.objects.filter(expires_at__lt=timezone.now()).delete()[0]
        if deleted:
            logger.info(f'Cleaned up {deleted} expired codes')
        return deleted


class UserSession(models.Model):
    """Tracks active user sessions for single-device enforcement."""

    user = models.ForeignKey('CustomUser', on_delete=models.CASCADE, related_name='sessions')
    session_key = models.CharField(max_length=100, unique=True)
    device_fingerprint = models.CharField(max_length=64)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    country = models.CharField(max_length=100, blank=True)
    city = models.CharField(max_length=100, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['session_key']),
            models.Index(fields=['device_fingerprint']),
            models.Index(fields=['last_activity']),
        ]
        ordering = ['-last_activity']

    def __str__(self):
        return f'Session for {self.user.username} - {self.created_at}'

    @classmethod
    def create_device_fingerprint(cls, request):
        fields = getattr(settings, 'SESSION_DEVICE_FINGERPRINT_FIELDS', [
            'HTTP_USER_AGENT', 'HTTP_X_FORWARDED_FOR', 'REMOTE_ADDR',
        ])
        data = ''.join(request.META.get(f, '') for f in fields)
        return hashlib.sha256(data.encode()).hexdigest()

    @classmethod
    def create_for_user(cls, user, request, session_key):
        fingerprint = cls.create_device_fingerprint(request)
        ip = TwoFactorCode.get_client_ip(request)
        ua = request.META.get('HTTP_USER_AGENT', '')

        if getattr(settings, 'SINGLE_DEVICE_SESSION', True):
            max_sessions = getattr(settings, 'MAX_CONCURRENT_SESSIONS', 1)
            active = cls.objects.filter(user=user, is_active=True).order_by('-last_activity')

            same_device = active.filter(device_fingerprint=fingerprint)
            if same_device.exists():
                # Same device — reuse the existing session record (allows multiple tabs)
                session = same_device.first()
                session.session_key = session_key
                session.last_activity = timezone.now()
                session.ip_address = ip
                session.save()
                return session

            # Different device — terminate older sessions if over the cap
            if active.count() >= max_sessions:
                for s in active[max_sessions - 1:]:
                    s.is_active = False
                    s.save()
                    logger.info(f'Terminated session {s.session_key} for {user.username}')

        return cls.objects.create(
            user=user,
            session_key=session_key,
            device_fingerprint=fingerprint,
            ip_address=ip,
            user_agent=ua,
        )

    def terminate(self):
        self.is_active = False
        self.save()

    @classmethod
    def cleanup_inactive(cls, days=30):
        cutoff = timezone.now() - timedelta(days=days)
        deleted = cls.objects.filter(
            Q(is_active=False) | Q(last_activity__lt=cutoff)
        ).delete()[0]
        if deleted:
            logger.info(f'Cleaned up {deleted} old sessions')
        return deleted
