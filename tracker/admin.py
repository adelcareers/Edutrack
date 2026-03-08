from django.contrib import admin
from .models import LessonLog, EvidenceFile


@admin.register(LessonLog)
class LessonLogAdmin(admin.ModelAdmin):
    """Admin view for lesson completion records with status and mastery filters."""

    list_display = ['scheduled_lesson', 'status', 'mastery', 'completed_at']
    list_filter = ['status', 'mastery']
    search_fields = ['scheduled_lesson__lesson__lesson_title']


@admin.register(EvidenceFile)
class EvidenceFileAdmin(admin.ModelAdmin):
    """Admin view for student-uploaded evidence files."""

    list_display = ['original_filename', 'lesson_log', 'uploaded_by', 'uploaded_at']
    list_filter = ['uploaded_at']
    search_fields = ['original_filename']
