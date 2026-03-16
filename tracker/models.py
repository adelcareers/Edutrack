from cloudinary.models import CloudinaryField
from django.contrib.auth.models import User
from django.db import models


class LessonLog(models.Model):
    """Tracks a student's completion status and mastery for a scheduled lesson.

    Created automatically when a lesson is scheduled; updated by the student
    as they work through each lesson.
    """

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("complete", "Complete"),
        ("skipped", "Skipped"),
    ]
    MASTERY_CHOICES = [
        ("unset", "Unset"),
        ("green", "Green"),
        ("amber", "Amber"),
        ("red", "Red"),
    ]

    scheduled_lesson = models.OneToOneField(
        "scheduler.ScheduledLesson", on_delete=models.CASCADE, related_name="log"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    mastery = models.CharField(max_length=10, choices=MASTERY_CHOICES, default="unset")
    student_notes = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    rescheduled_to = models.DateField(null=True, blank=True)
    updated_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)

    class Meta:
        verbose_name = "Lesson Log"
        verbose_name_plural = "Lesson Logs"

    def __str__(self):
        return f"{self.scheduled_lesson} — {self.status}"


class EvidenceFile(models.Model):
    """A file uploaded by a student as evidence for a completed lesson.

    Stored on Cloudinary via CloudinaryField. Supports any file type
    (image, PDF, video) by using resource_type='auto'.
    """

    lesson_log = models.ForeignKey(
        LessonLog, on_delete=models.CASCADE, related_name="evidence_files"
    )
    file = CloudinaryField("evidence", resource_type="auto")
    original_filename = models.CharField(max_length=255)
    uploaded_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]
        verbose_name = "Evidence File"
        verbose_name_plural = "Evidence Files"

    def __str__(self):
        return f"{self.original_filename} ({self.uploaded_at:%Y-%m-%d})"
