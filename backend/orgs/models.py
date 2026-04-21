"""
Multi-tenant org model for Critter — pared down from RateRail.

Removed: SuperUserAccess, ActiveOrganizationOverride, billing-tied member
addition/removal hooks (we'll wire those in Phase 5 with Stripe).

Kept: Organization + OrganizationMember (one user → one org via OneToOne) +
OrganizationInvitation with token + expiry + email tracking.
"""

import uuid
import logging
from datetime import timedelta

from django.db import models
from django.conf import settings
from django.utils.timezone import now
from django.core.exceptions import ValidationError

logger = logging.getLogger('auth_debug')


class OrganizationType(models.TextChoices):
    CREATOR = 'creator', 'Creator'    # solo creator
    AGENCY = 'agency', 'Agency'       # team managing multiple creators


class MemberRole(models.TextChoices):
    ADMIN = 'admin', 'Administrator'
    EDITOR = 'editor', 'Editor'
    VIEWER = 'viewer', 'Viewer'


class Organization(models.Model):
    name = models.CharField(max_length=200)
    org_type = models.CharField(
        max_length=10,
        choices=OrganizationType.choices,
        default=OrganizationType.CREATOR,
    )
    description = models.TextField(blank=True, null=True)
    website = models.URLField(blank=True, null=True)
    contact_email = models.EmailField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.name} ({self.get_org_type_display()})'

    def get_member_count(self):
        return self.members.count()

    def has_admin(self):
        return self.members.filter(role=MemberRole.ADMIN).exists()


class OrganizationMember(models.Model):
    """One-to-one: each user belongs to exactly one organization."""

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='members')
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='organization_membership',
    )
    role = models.CharField(max_length=10, choices=MemberRole.choices, default=MemberRole.VIEWER)
    joined_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.user.username} — {self.get_role_display()} at {self.organization.name}'

    def is_admin(self):
        return self.role == MemberRole.ADMIN

    def is_editor(self):
        return self.role in [MemberRole.ADMIN, MemberRole.EDITOR]

    def delete(self, *args, **kwargs):
        # Don't allow removing the last admin
        if (self.role == MemberRole.ADMIN and
                self.organization.members.filter(role=MemberRole.ADMIN).count() == 1):
            raise ValidationError('Cannot remove the last administrator')
        super().delete(*args, **kwargs)


class OrganizationInvitation(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='invitations')
    email = models.EmailField()
    token = models.CharField(max_length=100, unique=True, default=uuid.uuid4)
    role = models.CharField(max_length=10, choices=MemberRole.choices, default=MemberRole.VIEWER)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_invitations')
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    email_sent = models.BooleanField(default=False)
    email_sent_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f'Invitation for {self.email} to {self.organization.name}'

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = now() + timedelta(days=7)
        super().save(*args, **kwargs)

    def send_invitation_email(self, base_url):
        from django.core.mail import send_mail
        try:
            url = f'{base_url}/register?invite={self.token}'
            inviter = (
                f'{self.created_by.first_name} {self.created_by.last_name}'.strip()
                or self.created_by.username
            )
            subject = f"You're invited to join {self.organization.name} on Critter"
            body = (
                f'Hi there,\n\n'
                f'{inviter} invited you to join {self.organization.name} on Critter '
                f'as a {self.get_role_display()}.\n\n'
                f'Accept the invitation: {url}\n\n'
                f'This invitation expires on '
                f'{self.expires_at.strftime("%B %d, %Y")}.\n\n'
                f'— Critter'
            )
            send_mail(
                subject=subject,
                message=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[self.email],
                fail_silently=False,
            )
            self.email_sent = True
            self.email_sent_at = now()
            self.save(update_fields=['email_sent', 'email_sent_at'])
            return True
        except Exception as e:
            logger.error(f'Failed to send invitation to {self.email}: {e}')
            return False

    @classmethod
    def cleanup_expired(cls):
        return cls.objects.filter(expires_at__lt=now(), is_used=False).delete()[0]
