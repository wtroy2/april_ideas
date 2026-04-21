from django.contrib import admin
from .models import Organization, OrganizationMember, OrganizationInvitation


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ('name', 'org_type', 'created_at')
    list_filter = ('org_type',)
    search_fields = ('name', 'contact_email')


@admin.register(OrganizationMember)
class OrganizationMemberAdmin(admin.ModelAdmin):
    list_display = ('user', 'organization', 'role', 'joined_at')
    list_filter = ('role',)
    search_fields = ('user__username', 'user__email', 'organization__name')


@admin.register(OrganizationInvitation)
class OrganizationInvitationAdmin(admin.ModelAdmin):
    list_display = ('email', 'organization', 'role', 'created_at', 'expires_at', 'is_used')
    list_filter = ('role', 'is_used')
    search_fields = ('email', 'organization__name')
