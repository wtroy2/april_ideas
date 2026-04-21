from django.contrib import admin
from .models import StoryProject, StoryScene


class StorySceneInline(admin.TabularInline):
    model = StoryScene
    extra = 0
    readonly_fields = ('order', 'title', 'prompt', 'duration_seconds', 'desired_takes')


@admin.register(StoryProject)
class StoryProjectAdmin(admin.ModelAdmin):
    list_display = ('title', 'subject', 'status', 'target_duration_seconds', 'organization', 'created_at')
    list_filter = ('status', 'provider')
    search_fields = ('title', 'concept', 'subject__name')
    readonly_fields = ('uuid', 'created_at', 'updated_at', 'error_message')
    inlines = [StorySceneInline]


@admin.register(StoryScene)
class StorySceneAdmin(admin.ModelAdmin):
    list_display = ('project', 'order', 'title', 'duration_seconds', 'desired_takes', 'chosen_generation')
    list_filter = ('duration_seconds',)
    search_fields = ('title', 'prompt', 'project__title')
