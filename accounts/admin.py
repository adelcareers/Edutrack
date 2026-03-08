from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import UserProfile


class UserProfileInline(admin.StackedInline):
    """Inline editor for UserProfile shown inside the User admin detail view."""

    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Profile'


class UserAdmin(BaseUserAdmin):
    """Extended User admin that embeds the UserProfile inline."""

    inlines = (UserProfileInline,)


admin.site.unregister(User)
admin.site.register(User, UserAdmin)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """Admin view for UserProfile with role and subscription filters."""

    list_display = ['user', 'role', 'subscription_active', 'created_at']
    list_filter = ['role', 'subscription_active']
    search_fields = ['user__username', 'user__email']
