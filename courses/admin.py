from django.contrib import admin

from .models import (
    AssignmentType,
    Course,
    CourseArchive,
    CourseEnrollment,
    Label,
    Subject,
)


class AssignmentTypeInline(admin.TabularInline):
    model = AssignmentType
    extra = 0
    fields = ["name", "weight", "order"]


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "parent",
        "duration_weeks",
        "frequency_days",
        "grading_style",
        "is_archived",
        "created_at",
    ]
    list_filter = ["grading_style", "is_archived"]
    search_fields = ["name", "parent__username"]
    inlines = [AssignmentTypeInline]
    raw_id_fields = ["parent"]


@admin.register(CourseEnrollment)
class CourseEnrollmentAdmin(admin.ModelAdmin):
    list_display = ["course", "child", "start_date", "status", "enrolled_at"]
    list_filter = ["status"]
    search_fields = ["course__name", "child__first_name"]
    raw_id_fields = ["course", "child"]


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ["name", "parent"]
    search_fields = ["name", "parent__username"]
    raw_id_fields = ["parent"]


@admin.register(Label)
class LabelAdmin(admin.ModelAdmin):
    list_display = ["name", "color", "parent"]
    search_fields = ["name", "parent__username"]
    raw_id_fields = ["parent"]


@admin.register(CourseArchive)
class CourseArchiveAdmin(admin.ModelAdmin):
    list_display = ["course_name", "parent", "remark", "archived_at"]
    search_fields = ["course_name", "parent__username", "remark"]
    raw_id_fields = ["parent"]
