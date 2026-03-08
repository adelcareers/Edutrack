import uuid
from django.db import models
from django.contrib.auth.models import User
from cloudinary.models import CloudinaryField


class Report(models.Model):
    """A generated progress report for a child, optionally shared with an LA.

    Each report has a unique UUID share token. Sharing the token URL with a
    Local Authority grants read-only access without requiring authentication.
    The generated PDF is stored on Cloudinary.
    """

    TYPE_CHOICES = [
        ('summary', 'Summary'),
        ('portfolio', 'Full Portfolio'),
    ]

    child = models.ForeignKey('scheduler.Child', on_delete=models.CASCADE, related_name='reports')
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    report_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    date_from = models.DateField()
    date_to = models.DateField()
    share_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    token_expires_at = models.DateTimeField(null=True, blank=True)
    pdf_file = CloudinaryField('reports', blank=True, null=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Report'
        verbose_name_plural = 'Reports'

    def __str__(self):
        return f'{self.child} — {self.report_type} ({self.date_from} to {self.date_to})'
