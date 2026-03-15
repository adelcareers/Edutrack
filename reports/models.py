import uuid
from django.db import models
from django.contrib.auth.models import User
from django.db.models import Q
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


def default_grade_scale_bands():
    """Default letter-grade bands with GPA values."""
    return [
        {'letter': 'A', 'min': 90.0, 'max': 100.0, 'gpa': 4.0},
        {'letter': 'B', 'min': 80.0, 'max': 89.99, 'gpa': 3.0},
        {'letter': 'C', 'min': 70.0, 'max': 79.99, 'gpa': 2.0},
        {'letter': 'D', 'min': 60.0, 'max': 69.99, 'gpa': 1.0},
        {'letter': 'F', 'min': 0.0, 'max': 59.99, 'gpa': 0.0},
    ]


class GradeScaleProfile(models.Model):
    """Global or per-course grade scale definitions for a parent account."""

    parent = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='grade_scale_profiles',
    )
    course = models.ForeignKey(
        'courses.Course',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='grade_scale_profiles',
    )
    name = models.CharField(max_length=100, default='Default Scale')
    bands = models.JSONField(default=default_grade_scale_bands)
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['course_id', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=['parent', 'course'],
                name='reports_unique_parent_course_grade_scale',
            ),
            models.UniqueConstraint(
                fields=['parent'],
                condition=Q(course__isnull=True),
                name='reports_unique_parent_global_grade_scale',
            ),
        ]

    def __str__(self):
        if self.course_id:
            return f'{self.parent.username} / {self.course.name} grade scale'
        return f'{self.parent.username} / global grade scale'


class EnrollmentGradeSummary(models.Model):
    """Cached gradebook aggregate for one course enrollment."""

    enrollment = models.OneToOneField(
        'courses.CourseEnrollment',
        on_delete=models.CASCADE,
        related_name='grade_summary',
    )
    final_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    letter_grade = models.CharField(max_length=5, blank=True, default='')
    gpa_points = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    graded_assignments_count = models.PositiveIntegerField(default=0)
    total_assignments_count = models.PositiveIntegerField(default=0)
    missing_assignments_count = models.PositiveIntegerField(default=0)
    late_assignments_count = models.PositiveIntegerField(default=0)
    assignment_type_breakdown = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f'{self.enrollment.child.first_name} / {self.enrollment.course.name}'
