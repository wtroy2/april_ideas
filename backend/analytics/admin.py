from django.contrib import admin
from .models import RequestLog


@admin.register(RequestLog)
class RequestLogAdmin(admin.ModelAdmin):
    list_display = ('method', 'path', 'status_code', 'duration_ms', 'user', 'created_at')
    list_filter = ('method', 'status_code')
    search_fields = ('path', 'user__username', 'ip_address')
    readonly_fields = ('user', 'method', 'path', 'status_code', 'duration_ms',
                       'ip_address', 'user_agent', 'created_at')
