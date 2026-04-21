"""
Billing stub — Phase 5 will wire in Stripe subscriptions, plans, coupons,
and tie this to OrganizationMember.save() like RateRail does.

For now we expose just enough to track which plan an org is on so the
frontend can render a paywall before generation goes live.
"""

from django.db import models

from core.models import TimestampedModel


class PlanTier(models.TextChoices):
    FREE = 'free', 'Free trial'
    STARTER = 'starter', 'Starter'
    PRO = 'pro', 'Pro'
    AGENCY = 'agency', 'Agency'


class OrganizationBilling(TimestampedModel):
    """
    One row per Organization. Tracks current plan + Stripe IDs (filled in Phase 5).
    """
    organization = models.OneToOneField(
        'orgs.Organization', on_delete=models.CASCADE, related_name='billing'
    )
    plan = models.CharField(max_length=20, choices=PlanTier.choices, default=PlanTier.FREE)
    is_active = models.BooleanField(default=True)
    is_trial = models.BooleanField(default=True)
    trial_ends_at = models.DateTimeField(null=True, blank=True)

    # Generation quota for the current period
    monthly_generation_quota = models.IntegerField(default=10)
    generations_used_this_period = models.IntegerField(default=0)
    period_resets_at = models.DateTimeField(null=True, blank=True)

    # Stripe (Phase 5)
    stripe_customer_id = models.CharField(max_length=100, blank=True)
    stripe_subscription_id = models.CharField(max_length=100, blank=True)

    def has_quota_remaining(self):
        return self.generations_used_this_period < self.monthly_generation_quota

    def increment_usage(self, amount=1):
        self.generations_used_this_period = models.F('generations_used_this_period') + amount
        self.save(update_fields=['generations_used_this_period', 'updated_at'])

    def __str__(self):
        return f'{self.organization.name} - {self.get_plan_display()}'
