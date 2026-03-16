from cloudinary.models import CloudinaryField
from django.contrib.auth.models import User
from django.db import models


class UserProfile(models.Model):
    """Extended profile for every User. Links to Django's built-in User model.

    Stores the user's platform role (parent, student, or admin), an optional
    Cloudinary avatar, subscription tier, and storage limit in GB.
    """

    ROLE_CHOICES = [
        ("parent", "Parent"),
        ("student", "Student"),
        ("admin", "Admin"),
    ]

    TIER_CHOICES = [
        ("essential", "Essential"),
        ("premium", "Premium"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    avatar = CloudinaryField("avatar", blank=True, null=True)
    subscription_tier = models.CharField(
        max_length=20, choices=TIER_CHOICES, default="essential"
    )
    storage_limit_gb = models.IntegerField(default=20)  # in GB
    subscription_active = models.BooleanField(
        default=False
    )  # kept for backward compatibility
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"

    def __str__(self):
        return f"{self.user.username} ({self.role})"

    def get_storage_limit_gb(self):
        """Return storage limit in GB based on subscription tier."""
        return 200 if self.subscription_tier == "premium" else 20


class ParentSettings(models.Model):
    """Per-parent settings for calendar and assignment configuration."""

    WEEKDAY_CHOICES = [
        (0, "Monday"),
        (1, "Tuesday"),
        (2, "Wednesday"),
        (3, "Thursday"),
        (4, "Friday"),
        (5, "Saturday"),
        (6, "Sunday"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="settings")
    first_day_of_week = models.PositiveSmallIntegerField(
        choices=WEEKDAY_CHOICES, default=0
    )
    show_empty_assignments = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Parent Settings"
        verbose_name_plural = "Parent Settings"

    def __str__(self):
        return f"Settings for {self.user.username}"
