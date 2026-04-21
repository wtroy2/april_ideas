from django.contrib import admin
from .models import Theme


@admin.register(Theme)
class ThemeAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'organization', 'is_active', 'is_featured', 'shot_style', 'music_vibe')
    list_filter = ('shot_style', 'music_vibe', 'is_active', 'is_featured')
    search_fields = ('name', 'slug', 'description', 'tags')
    readonly_fields = ('uuid', 'created_at', 'updated_at')
