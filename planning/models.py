from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from courses.models import AssignmentType, Course, CourseEnrollment


class CourseAssignmentTemplate(models.Model):
    """A reusable planning template for a course item."""

    ITEM_KIND_ASSIGNMENT = "assignment"
    ITEM_KIND_ACTIVITY = "activity"
    ITEM_KIND_LESSON = "lesson"
    ITEM_KIND_CHOICES = [
        (ITEM_KIND_ASSIGNMENT, "Assignment"),
        (ITEM_KIND_ACTIVITY, "Activity"),
        (ITEM_KIND_LESSON, "Lesson"),
    ]

    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name="assignment_templates"
    )
    assignment_type = models.ForeignKey(
        AssignmentType,
        on_delete=models.CASCADE,
        related_name="templates",
        null=True,
        blank=True,
    )
    item_kind = models.CharField(
        max_length=20,
        choices=ITEM_KIND_CHOICES,
        default=ITEM_KIND_ASSIGNMENT,
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    is_graded = models.BooleanField(default=False)
    due_offset_days = models.IntegerField(default=0)
    order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return f"{self.course.name} - {self.name}"


class PlanItem(models.Model):
    ITEM_TYPE_LESSON = "lesson"
    ITEM_TYPE_ASSIGNMENT = "assignment"
    ITEM_TYPE_ACTIVITY = "activity"
    ITEM_TYPE_CHOICES = [
        (ITEM_TYPE_LESSON, "Lesson"),
        (ITEM_TYPE_ASSIGNMENT, "Assignment"),
        (ITEM_TYPE_ACTIVITY, "Activity"),
    ]

    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name="plan_items"
    )
    item_type = models.CharField(max_length=20, choices=ITEM_TYPE_CHOICES)
    week_number = models.PositiveSmallIntegerField()
    day_number = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=300)
    description = models.TextField(blank=True, default="")
    notes = models.TextField(blank=True, default="")
    order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["week_number", "day_number", "order"]

    def __str__(self):
        return f"{self.course.name} - W{self.week_number} D{self.day_number} [{self.item_type}]"


class LessonPlanDetail(models.Model):
    plan_item = models.OneToOneField(
        PlanItem, on_delete=models.CASCADE, related_name="lesson_detail"
    )
    course_subject = models.ForeignKey(
        "courses.CourseSubjectConfig",
        on_delete=models.CASCADE,
        related_name="lesson_plans",
    )
    curriculum_lesson = models.ForeignKey(
        "curriculum.Lesson",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="plan_details",
    )

    def __str__(self):
        return f"Lesson detail for {self.plan_item}"


class AssignmentPlanDetail(models.Model):
    plan_item = models.OneToOneField(
        PlanItem, on_delete=models.CASCADE, related_name="assignment_detail"
    )
    assignment_type = models.ForeignKey(
        AssignmentType, on_delete=models.CASCADE, related_name="new_plan_details"
    )
    is_graded = models.BooleanField(default=False)
    due_offset_days = models.IntegerField(default=0)

    def __str__(self):
        return f"Assignment detail for {self.plan_item}"


class ActivityPlanDetail(models.Model):
    plan_item = models.OneToOneField(
        PlanItem, on_delete=models.CASCADE, related_name="activity_detail"
    )
    goal = models.TextField(blank=True, default="")
    objective = models.TextField(blank=True, default="")
    course_subject = models.ForeignKey(
        "courses.CourseSubjectConfig",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="activity_plans",
    )
    unit_title = models.CharField(max_length=300, blank=True, default="")
    due_offset_days = models.IntegerField(default=0)

    def __str__(self):
        return f"Activity detail for {self.plan_item}"


class AssignmentPlanItem(models.Model):
    """A planned assignment slot in a course week/day grid."""

    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name="assignment_plan_items"
    )
    template = models.ForeignKey(
        CourseAssignmentTemplate, on_delete=models.CASCADE, related_name="plan_items"
    )
    week_number = models.PositiveSmallIntegerField()
    day_number = models.PositiveSmallIntegerField()
    due_in_days = models.PositiveSmallIntegerField(default=0)
    order = models.IntegerField(default=0)
    notes = models.TextField(blank=True, default="")
    lesson_child = models.ForeignKey(
        "scheduler.Child",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="lesson_plan_items",
    )
    lesson_enrolled_subject = models.ForeignKey(
        "scheduler.EnrolledSubject",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="lesson_plan_items",
    )
    scheduled_lesson = models.ForeignKey(
        "scheduler.ScheduledLesson",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="plan_items",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["week_number", "day_number", "order"]

    def __str__(self):
        return f"{self.course.name} - W{self.week_number} D{self.day_number}"


class StudentAssignment(models.Model):
    """Student-specific instance of a planned assignment."""

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("needs_grading", "Needs Grading"),
        ("complete", "Complete"),
        ("overdue", "Overdue"),
    ]

    enrollment = models.ForeignKey(
        CourseEnrollment, on_delete=models.CASCADE, related_name="assignments"
    )
    plan_item = models.ForeignKey(
        AssignmentPlanItem,
        on_delete=models.CASCADE,
        related_name="student_assignments",
        null=True,
        blank=True,
    )
    due_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
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
        help_text="Direct percentage entry when grading style is percent-based.",
    )
    graded_at = models.DateTimeField(null=True, blank=True)
    graded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="graded_assignments",
    )
    grading_notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    # Bridge to PlanItem (new unified planning model)
    new_plan_item = models.ForeignKey(
        "PlanItem",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="student_assignments_new",
    )

    class Meta:
        ordering = ["due_date", "status"]

    def __str__(self):
        return f"{self.enrollment.child.first_name} - {self.plan_item}"


class AssignmentAttachment(models.Model):
    """Files attached to a planned assignment."""

    plan_item = models.ForeignKey(
        AssignmentPlanItem,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    file = models.FileField(upload_to="plan_attachments/")
    original_name = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.original_name or self.file.name


class AssignmentComment(models.Model):
    """Shared discussion thread entries for a student assignment."""

    assignment = models.ForeignKey(
        StudentAssignment,
        on_delete=models.CASCADE,
        related_name="comments",
    )
    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="assignment_comments",
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Comment by {self.author.username} on assignment {self.assignment_id}"


class AssignmentSubmission(models.Model):
    """Files submitted by a student for a specific assignment."""

    assignment = models.ForeignKey(
        StudentAssignment,
        on_delete=models.CASCADE,
        related_name="submissions",
    )
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="assignment_submissions",
    )
    file = models.FileField(upload_to="assignment_submissions/")
    original_name = models.CharField(max_length=255, blank=True, default="")
    content_type = models.CharField(max_length=120, blank=True, default="")
    file_size = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.original_name or self.file.name


class ActivityProgress(models.Model):
    """Child-level progress tracking for planned activity items."""

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("complete", "Complete"),
    ]

    enrollment = models.ForeignKey(
        CourseEnrollment,
        on_delete=models.CASCADE,
        related_name="activity_progress_items",
    )
    plan_item = models.ForeignKey(
        AssignmentPlanItem,
        on_delete=models.CASCADE,
        related_name="activity_progress_items",
        null=True,
        blank=True,
    )
    # Bridge for new unified PlanItem model (nullable during migration)
    new_plan_item = models.ForeignKey(
        "PlanItem",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="activity_progress_new",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    notes = models.TextField(blank=True, default="")
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["enrollment__child__first_name", "created_at"]
        unique_together = [("enrollment", "plan_item")]

    def __str__(self):
        return f"{self.enrollment.child.first_name} - {self.plan_item}"
    


class ActivityProgressAttachment(models.Model):
    """Evidence attached to an activity progress row."""

    progress = models.ForeignKey(
        ActivityProgress,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    file = models.FileField(
        upload_to="activity_progress_attachments/", null=True, blank=True
    )
    original_name = models.CharField(max_length=255, blank=True, default="")
    external_url = models.URLField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return (
            self.original_name
            or self.external_url
            or (self.file.name if self.file else f"Activity attachment {self.pk}")
        )
