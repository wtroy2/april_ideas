from django.contrib import admin
from .models import OrganizationBilling


@admin.register(OrganizationBilling)
class OrganizationBillingAdmin(admin.ModelAdmin):
    list_display = ('organization', 'plan', 'is_active', 'is_trial',
                    'monthly_generation_quota', 'generations_used_this_period')
    list_filter = ('plan', 'is_active', 'is_trial')
    search_fields = ('organization__name', 'stripe_customer_id')
