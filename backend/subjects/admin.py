from django.contrib import admin
from .models import Subject, SubjectPhoto


class SubjectPhotoInline(admin.TabularInline):
    model = SubjectPhoto
    extra = 0
    readonly_fields = ('asset', 'created_at')


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'kind', 'species', 'organization', 'is_archived', 'created_at')
    list_filter = ('kind', 'species', 'is_archived')
    search_fields = ('name', 'organization__name', 'auto_description', 'user_description')
    readonly_fields = ('uuid', 'created_at', 'updated_at')
    inlines = [SubjectPhotoInline]
