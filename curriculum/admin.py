from django.contrib import admin
from .models import Lesson


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    """Admin view for Oak National Academy lessons with search and key-stage filter."""

    list_display = ['lesson_title', 'subject_name', 'year', 'key_stage', 'unit_title']
    search_fields = ['lesson_title', 'subject_name', 'unit_title']
    list_filter = ['key_stage', 'year', 'subject_name']
