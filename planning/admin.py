from django.contrib import admin

from .models import (
    ActivityPlanDetail,
    AssignmentPlanDetail,
    LessonPlanDetail,
    PlanItem,
)


@admin.register(PlanItem)
class PlanItemAdmin(admin.ModelAdmin):
    list_display = ["course", "item_type", "week_number", "day_number", "is_active"]
    list_filter = ["item_type", "is_active"]
    search_fields = ["course__name", "name"]
    raw_id_fields = ["course"]


@admin.register(LessonPlanDetail)
class LessonPlanDetailAdmin(admin.ModelAdmin):
    list_display = ["plan_item", "course_subject", "curriculum_lesson"]
    raw_id_fields = ["plan_item", "course_subject", "curriculum_lesson"]


@admin.register(AssignmentPlanDetail)
class AssignmentPlanDetailAdmin(admin.ModelAdmin):
    list_display = ["plan_item", "assignment_type", "is_graded"]
    raw_id_fields = ["plan_item", "assignment_type"]


@admin.register(ActivityPlanDetail)
class ActivityPlanDetailAdmin(admin.ModelAdmin):
    list_display = ["plan_item", "course_subject", "unit_title"]
    raw_id_fields = ["plan_item", "course_subject"]
