from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import CustomUser, TwoFactorCode, UserSession


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('Critter profile', {'fields': ('phone', 'avatar_url')}),
    )
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'date_joined')
    search_fields = ('username', 'email', 'first_name', 'last_name')


@admin.register(TwoFactorCode)
class TwoFactorCodeAdmin(admin.ModelAdmin):
    list_display = ('user', 'code_type', 'created_at', 'expires_at', 'is_used', 'attempts')
    list_filter = ('code_type', 'is_used')
    search_fields = ('user__username', 'user__email', 'session_id')
    readonly_fields = ('code', 'created_at', 'used_at', 'ip_address', 'user_agent')


@admin.register(UserSession)
class UserSessionAdmin(admin.ModelAdmin):
    list_display = ('user', 'ip_address', 'created_at', 'last_activity', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('user__username', 'user__email', 'session_key', 'ip_address')
    readonly_fields = ('session_key', 'device_fingerprint', 'created_at', 'last_activity')
