from django.db import models
from django.contrib.auth.models import User
from cloudinary.models import CloudinaryField


class UserProfile(models.Model):
    """Extended profile for every User. Links to Django's built-in User model.

    Stores the user's platform role (parent, student, or admin), an optional
    Cloudinary avatar, and whether the parent's subscription is currently active.
    """

    ROLE_CHOICES = [
        ('parent', 'Parent'),
        ('student', 'Student'),
        ('admin', 'Admin'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    avatar = CloudinaryField('avatar', blank=True, null=True)
    subscription_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'User Profile'
        verbose_name_plural = 'User Profiles'

    def __str__(self):
        return f'{self.user.username} ({self.role})'
