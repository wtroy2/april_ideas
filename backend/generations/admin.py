from django.contrib import admin
from .models import GenerationBatch, Generation, AudioMix


class GenerationInline(admin.TabularInline):
    model = Generation
    extra = 0
    readonly_fields = ('uuid', 'scenario', 'status', 'started_at', 'finished_at',
                       'error_message', 'video_asset', 'rendered_prompt')


@admin.register(GenerationBatch)
class GenerationBatchAdmin(admin.ModelAdmin):
    list_display = ('uuid', 'subject', 'theme', 'provider', 'status',
                    'organization', 'created_at')
    list_filter = ('provider', 'status')
    search_fields = ('uuid', 'subject__name', 'theme__name', 'organization__name')
    readonly_fields = ('uuid', 'created_at', 'updated_at')
    inlines = [GenerationInline]


@admin.register(Generation)
class GenerationAdmin(admin.ModelAdmin):
    list_display = ('uuid', 'batch', 'scenario', 'take_index', 'status', 'started_at', 'finished_at')
    list_filter = ('status',)
    search_fields = ('uuid', 'scenario', 'rendered_prompt', 'caption')
    readonly_fields = ('uuid', 'rendered_prompt', 'started_at', 'finished_at',
                       'error_message', 'rq_job_id', 'created_at', 'updated_at')


@admin.register(AudioMix)
class AudioMixAdmin(admin.ModelAdmin):
    list_display = ('uuid', 'generation', 'music_track', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('uuid', 'generation__uuid', 'music_track__original_filename')
    readonly_fields = ('uuid', 'output_asset', 'created_at', 'updated_at')
