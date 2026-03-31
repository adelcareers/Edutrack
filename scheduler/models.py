from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

DAYS_DEFAULT = "0,1,2,3,4"


class CustomSubjectGroup(models.Model):
    """Groups custom lessons created by a parent under a named subject.

    When a parent adds lessons manually or via CSV, all lessons in that
    batch are linked back to one of these groups for easy management
    (bulk delete, rename, etc.).
    """

    parent = models.ForeignKey(
        "auth.User", on_delete=models.CASCADE, related_name="custom_subject_groups"
    )
    subject_name = models.CharField(max_length=100)
    year = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["subject_name"]
        verbose_name = "Custom Subject Group"
        verbose_name_plural = "Custom Subject Groups"

    def __str__(self):
        return f"{self.subject_name} ({self.year}) — {self.parent.username}"


class Child(models.Model):
    """A home-educated child registered by a parent user.

    Links to the parent's User account and optionally to a student-role User
    so the child can log in and view their own calendar.
    """

    parent = models.ForeignKey(User, on_delete=models.CASCADE, related_name="children")
    first_name = models.CharField(max_length=100)
    photo = models.ImageField(upload_to="student_photos/", blank=True, null=True)
    birth_month = models.IntegerField(
        choices=[(i, i) for i in range(1, 13)],
        null=True,
        blank=True,
    )
    birth_year = models.IntegerField(null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    school_year = models.CharField(max_length=20, blank=True, default="")
    academic_year_start = models.DateField()
    student_user = models.OneToOneField(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="child_profile",
    )
    is_active = models.BooleanField(default=True)
    is_setup_complete = models.BooleanField(default=True)
    onboarding_updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Child"
        verbose_name_plural = "Children"

    def __str__(self):
        return f"{self.first_name} (Year {self.school_year}, parent: {self.parent.username})"


class EnrolledSubject(models.Model):
    """A subject that a child is enrolled in for the academic year.

    Stores how many lessons per week the parent wants scheduled, and a colour
    hex code used to display the subject on the calendar.
    """

    child = models.ForeignKey(
        Child, on_delete=models.CASCADE, related_name="enrolled_subjects"
    )
    subject_name = models.CharField(max_length=100)
    key_stage = models.CharField(max_length=10)
    lessons_per_week = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(10)]
    )
    colour_hex = models.CharField(max_length=7)
    # List of weekday ints (0=Mon … 4=Fri) that this subject is taught on.
    days_of_week = models.JSONField(default=list)
    # When set, lessons are pulled from this year rather than child.school_year.
    source_year = models.CharField(max_length=20, blank=True, default="")
    # Canonical source subject key (e.g. "Maths") for imported/display labels.
    source_subject_name = models.CharField(max_length=100, blank=True, default="")
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Enrolled Subject"
        verbose_name_plural = "Enrolled Subjects"

    def __str__(self):
        return f"{self.child.first_name} — {self.subject_name} ({self.lessons_per_week}/wk)"


class ScheduledLesson(models.Model):
    """A curriculum lesson assigned to a specific date for a child.

    Created in bulk by the scheduling engine. Each record ties a Lesson from the
    Oak curriculum to a child's calendar on a particular date.
    """

    child = models.ForeignKey(
        Child, on_delete=models.CASCADE, related_name="scheduled_lessons"
    )
    lesson = models.ForeignKey("curriculum.Lesson", on_delete=models.CASCADE)
    enrolled_subject = models.ForeignKey(EnrolledSubject, on_delete=models.CASCADE)
    scheduled_date = models.DateField(db_index=True)
    order_on_day = models.IntegerField(default=0)
    # Bridge to the new PlanItem / CourseSubjectConfig models (added in Phase 1)
    plan_item = models.ForeignKey(
        "planning.PlanItem",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="scheduled_lessons",
    )
    course_subject = models.ForeignKey(
        "courses.CourseSubjectConfig",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="scheduled_lessons",
    )

    class Meta:
        ordering = ["scheduled_date", "order_on_day"]
        verbose_name = "Scheduled Lesson"
        verbose_name_plural = "Scheduled Lessons"

    def __str__(self):
        return f"{self.child.first_name} — {self.lesson.lesson_title} on {self.scheduled_date}"


class Vacation(models.Model):
    """A vacation or break period for a specific child.

    Lessons that fall on vacation days are visually marked on the calendar
    but not automatically rescheduled.  Parents can add, edit or delete
    vacations via the Manage Vacations page.
    """

    child = models.ForeignKey(Child, on_delete=models.CASCADE, related_name="vacations")
    name = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()

    class Meta:
        ordering = ["start_date"]
        verbose_name = "Vacation"
        verbose_name_plural = "Vacations"

    def __str__(self):
        return f"{self.child.first_name} — {self.name} ({self.start_date} → {self.end_date})"
