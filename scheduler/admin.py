from django.contrib import admin

from .models import Child, EnrolledSubject, ScheduledLesson


@admin.register(Child)
class ChildAdmin(admin.ModelAdmin):
    """Admin view for children registered by parents."""

    list_display = ["first_name", "school_year", "parent", "is_active"]
    list_filter = ["school_year", "is_active"]
    search_fields = ["first_name", "parent__username"]


@admin.register(EnrolledSubject)
class EnrolledSubjectAdmin(admin.ModelAdmin):
    """Admin view for subjects enrolled by a child."""

    list_display = [
        "child",
        "subject_name",
        "key_stage",
        "lessons_per_week",
        "is_active",
    ]
    list_filter = ["key_stage", "is_active"]
    search_fields = ["subject_name", "child__first_name"]


@admin.register(ScheduledLesson)
class ScheduledLessonAdmin(admin.ModelAdmin):
    """Admin view for auto-generated lesson schedule entries."""

    list_display = ["child", "lesson", "scheduled_date", "order_on_day"]
    list_filter = ["scheduled_date"]
    search_fields = ["child__first_name", "lesson__lesson_title"]
