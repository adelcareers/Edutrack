from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from courses.models import AssignmentType, Course, CourseEnrollment


class CourseAssignmentTemplate(models.Model):
    """A reusable assignment template for a course."""

    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name='assignment_templates'
    )
    assignment_type = models.ForeignKey(
        AssignmentType, on_delete=models.PROTECT, related_name='templates'
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    is_graded = models.BooleanField(default=False)
    due_offset_days = models.IntegerField(default=0)
    order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'name']

    def __str__(self):
        return f'{self.course.name} - {self.name}'


class AssignmentPlanItem(models.Model):
    """A planned assignment slot in a course week/day grid."""

    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name='assignment_plan_items'
    )
    template = models.ForeignKey(
        CourseAssignmentTemplate, on_delete=models.CASCADE, related_name='plan_items'
    )
    week_number = models.PositiveSmallIntegerField()
    day_number = models.PositiveSmallIntegerField()
    due_in_days = models.PositiveSmallIntegerField(default=0)
    order = models.IntegerField(default=0)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['week_number', 'day_number', 'order']

    def __str__(self):
        return f'{self.course.name} - W{self.week_number} D{self.day_number}'


class StudentAssignment(models.Model):
    """Student-specific instance of a planned assignment."""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('complete', 'Complete'),
        ('overdue', 'Overdue'),
    ]

    enrollment = models.ForeignKey(
        CourseEnrollment, on_delete=models.CASCADE, related_name='assignments'
    )
    plan_item = models.ForeignKey(
        AssignmentPlanItem, on_delete=models.CASCADE, related_name='student_assignments'
    )
    due_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    completed_at = models.DateTimeField(null=True, blank=True)
    score = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    points_available = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    score_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='Direct percentage entry when grading style is percent-based.',
    )
    graded_at = models.DateTimeField(null=True, blank=True)
    graded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='graded_assignments',
    )
    grading_notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['due_date', 'status']

    def __str__(self):
        return f'{self.enrollment.child.first_name} - {self.plan_item}'


class AssignmentAttachment(models.Model):
    """Files attached to a planned assignment."""

    plan_item = models.ForeignKey(
        AssignmentPlanItem,
        on_delete=models.CASCADE,
        related_name='attachments',
    )
    file = models.FileField(upload_to='plan_attachments/')
    original_name = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.original_name or self.file.name
