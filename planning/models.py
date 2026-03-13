from django.db import models

from courses.models import Course, CourseEnrollment, GlobalAssignmentType


class CourseAssignmentType(models.Model):
    """Per-course overrides of global assignment types."""

    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name='assignment_type_overrides'
    )
    global_type = models.ForeignKey(
        GlobalAssignmentType, on_delete=models.SET_NULL, null=True, blank=True
    )
    name = models.CharField(max_length=100)
    color = models.CharField(max_length=7, default='#9ca3af')
    is_hidden = models.BooleanField(default=False)
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ['order', 'name']
        unique_together = [('course', 'name')]

    def __str__(self):
        return f'{self.course.name} - {self.name}'


class CourseAssignmentTemplate(models.Model):
    """A reusable assignment template for a course."""

    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name='assignment_templates'
    )
    assignment_type = models.ForeignKey(
        CourseAssignmentType, on_delete=models.PROTECT, related_name='templates'
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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['due_date', 'status']

    def __str__(self):
        return f'{self.enrollment.child.first_name} - {self.plan_item}'
