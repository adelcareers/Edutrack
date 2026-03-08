from django.contrib import admin
from .models import Report


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    """Admin view for generated progress reports with LA share tokens."""

    list_display = ['child', 'report_type', 'created_at', 'share_token', 'created_by']
    list_filter = ['report_type']
    search_fields = ['child__first_name', 'created_by__username']
    readonly_fields = ['share_token', 'created_at']
