from django.contrib import admin
from .models import Asset


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ('uuid', 'kind', 'status', 'organization', 'size_bytes', 'created_at')
    list_filter = ('kind', 'status')
    search_fields = ('uuid', 'object_key', 'original_filename', 'organization__name')
    readonly_fields = ('uuid', 'created_at', 'updated_at', 'scan_started_at',
                       'scan_completed_at', 'scan_result')
