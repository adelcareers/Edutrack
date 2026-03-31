from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

try:
    from cloudinary.models import CloudinaryField
except ImportError:
    CloudinaryField = None  # fallback if cloudinary not installed in test env


GRADE_YEAR_CHOICES = [
    ("EYFS", "Early years foundation stage"),
    ("1", "Year 1"),
    ("2", "Year 2"),
    ("3", "Year 3"),
    ("4", "Year 4"),
    ("5", "Year 5"),
    ("6", "Year 6"),
    ("7", "Year 7"),
    ("8", "Year 8"),
    ("9", "Year 9"),
    ("10", "Year 10"),
    ("11", "Year 11"),
]

GRADE_YEAR_LABELS = {k: v for k, v in GRADE_YEAR_CHOICES}
LEGACY_GRADE_YEAR_KEY_MAP = {
    "preschool": "EYFS",
    "prek": "EYFS",
    "k": "EYFS",
    "year1": "1",
    "year2": "2",
    "year3": "3",
    "year4": "4",
    "year5": "5",
    "year6": "6",
    "year7": "7",
    "year8": "8",
    "year9": "9",
    "year10": "10",
    "year11": "11",
}

for _legacy_key, _normalized_key in LEGACY_GRADE_YEAR_KEY_MAP.items():
    GRADE_YEAR_LABELS.setdefault(
        _legacy_key, GRADE_YEAR_LABELS.get(_normalized_key, _normalized_key)
    )

GRADING_STYLE_CHOICES = [
    ("not_graded", "Not Graded"),
    ("point_graded", "Point Graded"),
    ("percent_graded", "Percent Graded"),
]

DEFAULT_ASSIGNMENT_TYPES = ["Homework", "Quiz", "Test", "Paper", "Lab", "Other"]
GLOBAL_ASSIGNMENT_DEFAULTS = [
    ("Homework", "#9ca3af"),
    ("Quiz", "#60a5fa"),
    ("Test", "#fca5a5"),
    ("Paper", "#5eead4"),
    ("Lab", "#86efac"),
    ("Other", "#c4b5fd"),
]


class GlobalAssignmentType(models.Model):
    """Assignment types shared across all courses for a parent account."""

    parent = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="global_assignment_types"
    )
    name = models.CharField(max_length=100)
    color = models.CharField(max_length=7, default="#9ca3af")
    is_hidden = models.BooleanField(default=False)
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]
        unique_together = [("parent", "name")]

    def __str__(self):
        return f"{self.name} ({self.parent.username})"


class Subject(models.Model):
    """A parent-scoped subject tag (e.g. "Maths", "English")."""

    parent = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="course_subjects"
    )
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ["name"]
        unique_together = [("parent", "name")]

    def __str__(self):
        return self.name


class Label(models.Model):
    """A parent-scoped coloured label for organising courses."""

    parent = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="course_labels"
    )
    name = models.CharField(max_length=100)
    color = models.CharField(max_length=7, default="#6c757d")

    class Meta:
        ordering = ["name"]
        unique_together = [("parent", "name")]

    def __str__(self):
        return self.name


class Course(models.Model):
    """A reusable course template created by a parent.

    A course has no fixed start / end date until a student is enrolled.
    It defines the structure (duration, frequency, grading) and can be
    enrolled for multiple students or reused across years.
    """

    parent = models.ForeignKey(User, on_delete=models.CASCADE, related_name="courses")
    student_owner = models.ForeignKey(
        "scheduler.Child",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="workspace_courses",
    )
    name = models.CharField(max_length=200)
    color = models.CharField(max_length=7, default="#6c757d")

    if CloudinaryField is not None:
        photo = CloudinaryField("course_photo", blank=True, null=True)
    else:
        photo = models.ImageField(upload_to="course_photos/", blank=True, null=True)

    subjects = models.ManyToManyField(Subject, blank=True, related_name="courses")
    labels = models.ManyToManyField(Label, blank=True, related_name="courses")

    # Grade years stored as a comma-separated string of GRADE_YEAR_CHOICES keys
    grade_years = models.CharField(max_length=200, blank=True, default="")

    duration_weeks = models.IntegerField(
        default=36,
        validators=[MinValueValidator(1), MaxValueValidator(52)],
    )
    frequency_days = models.IntegerField(
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(7)],
    )
    # Default days of week: Mon=0 … Sun=6, used to pre-populate enrollment
    default_days = models.JSONField(default=list)

    grading_style = models.CharField(
        max_length=20,
        choices=GRADING_STYLE_CHOICES,
        default="not_graded",
    )
    use_assignment_weights = models.BooleanField(default=False)
    credits = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)

    description = models.TextField(blank=True, default="")
    course_intro = models.TextField(blank=True, default="")

    is_archived = models.BooleanField(default=False, db_index=True)
    is_student_workspace = models.BooleanField(default=False, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    def get_grade_year_labels(self):
        """Return a list of human-readable grade year strings."""
        if not self.grade_years:
            return []
        return [
            GRADE_YEAR_LABELS.get(gy.strip(), gy.strip())
            for gy in self.grade_years.split(",")
            if gy.strip()
        ]

    def get_default_days_list(self):
        """Return default_days as a list of integers."""
        return list(self.default_days) if self.default_days else []

    @property
    def active_enrollments_count(self):
        return self.enrollments.filter(status="active").count()


class CourseSubjectConfig(models.Model):
    SOURCE_CHOICES = [("oak", "Oak"), ("custom", "Custom"), ("csv", "CSV")]

    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name="subject_configs"
    )
    subject_name = models.CharField(max_length=100)
    key_stage = models.CharField(max_length=10, blank=True, default="")
    year = models.CharField(max_length=20, blank=True, default="")
    lessons_per_week = models.IntegerField(
        default=3, validators=[MinValueValidator(1), MaxValueValidator(10)]
    )
    days_of_week = models.JSONField(default=list)
    colour_hex = models.CharField(max_length=7, default="#6c757d")
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default="oak")
    source_subject_name = models.CharField(max_length=100, blank=True, default="")
    source_year = models.CharField(max_length=20, blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("course", "subject_name")]
        ordering = ["subject_name"]

    def __str__(self):
        return f"{self.course.name} - {self.subject_name}"


class CourseSubjectScheduleSlot(models.Model):
    """Draft timetable slot for a course subject."""

    course_subject = models.ForeignKey(
        CourseSubjectConfig,
        on_delete=models.CASCADE,
        related_name="schedule_slots",
    )
    weekday = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(6)]
    )
    period = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(12)]
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["weekday", "period", "id"]
        unique_together = [("course_subject", "weekday", "period")]

    def __str__(self):
        return f"{self.course_subject.subject_name} @ {self.weekday}:{self.period}"


class AssignmentType(models.Model):
    """An assignment category with an optional grade weight for a course."""

    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name="assignment_types"
    )
    global_type = models.ForeignKey(
        GlobalAssignmentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="course_assignment_types",
    )
    name = models.CharField(max_length=100)
    color = models.CharField(max_length=7, default="#9ca3af")
    is_hidden = models.BooleanField(default=False)
    weight = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    default_points_available = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="Default points available for assignments of this type.",
    )
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return f"{self.name} ({self.weight}%)"


def seed_global_assignment_types(user):
    """Seed the default global assignment types for a given user."""
    if GlobalAssignmentType.objects.filter(parent=user).exists():
        return
    to_create = [
        GlobalAssignmentType(
            parent=user,
            name=name,
            color=color,
            order=idx,
        )
        for idx, (name, color) in enumerate(GLOBAL_ASSIGNMENT_DEFAULTS)
    ]
    GlobalAssignmentType.objects.bulk_create(to_create)


def sync_course_assignment_types_from_global(course):
    """Sync a course's assignment types from the parent's global type list.

    This enforces a single source of truth for type definitions (name/color/
    visibility/order) while preserving course-specific weights.
    """
    seed_global_assignment_types(course.parent)

    global_types = list(
        GlobalAssignmentType.objects.filter(parent=course.parent).order_by(
            "order", "name"
        )
    )
    global_ids = {gt.pk for gt in global_types}

    existing = list(AssignmentType.objects.filter(course=course))
    by_global_id = {at.global_type_id: at for at in existing if at.global_type_id}

    # Legacy rows created before global linking can be adopted by name.
    by_legacy_name = {}
    for at in existing:
        if at.global_type_id is None:
            key = (at.name or "").strip().lower()
            if key and key not in by_legacy_name:
                by_legacy_name[key] = at

    kept_ids = set()
    for gt in global_types:
        at = by_global_id.get(gt.pk)
        if at is None:
            at = by_legacy_name.get(gt.name.strip().lower())

        if at is None:
            at = AssignmentType.objects.create(
                course=course,
                global_type=gt,
                name=gt.name,
                color=gt.color,
                is_hidden=gt.is_hidden,
                weight=0,
                order=gt.order,
            )
        else:
            changed = []
            if at.global_type_id != gt.pk:
                at.global_type = gt
                changed.append("global_type")
            if at.name != gt.name:
                at.name = gt.name
                changed.append("name")
            if at.color != gt.color:
                at.color = gt.color
                changed.append("color")
            # Global hidden always wins; otherwise preserve per-course visibility.
            if gt.is_hidden and not at.is_hidden:
                at.is_hidden = gt.is_hidden
                changed.append("is_hidden")
            if at.order != gt.order:
                at.order = gt.order
                changed.append("order")
            if changed:
                at.save(update_fields=changed)

        kept_ids.add(at.pk)

    # Rows no longer represented by global settings are removed unless in use.
    for at in existing:
        if at.pk in kept_ids:
            continue

        has_templates = at.templates.exists()
        if has_templates:
            changed = []
            if at.is_hidden is not True:
                at.is_hidden = True
                changed.append("is_hidden")
            if at.global_type_id in global_ids or at.global_type_id is not None:
                at.global_type = None
                changed.append("global_type")
            if changed:
                at.save(update_fields=changed)
        else:
            at.delete()


ENROLLMENT_STATUS_CHOICES = [
    ("active", "Active"),
    ("completed", "Completed"),
    ("unenrolled", "Unenrolled"),
]

DAY_CHOICES = [
    ("0", "Mon"),
    ("1", "Tue"),
    ("2", "Wed"),
    ("3", "Thu"),
    ("4", "Fri"),
    ("5", "Sat"),
    ("6", "Sun"),
]


class CourseEnrollment(models.Model):
    """Links a Child to a Course for a specific start date and set of weekdays."""

    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name="enrollments"
    )
    child = models.ForeignKey(
        "scheduler.Child", on_delete=models.CASCADE, related_name="course_enrollments"
    )
    start_date = models.DateField()
    # List of chosen weekday ints, e.g. [0, 2, 4] for Mon/Wed/Fri
    days_of_week = models.JSONField(default=list)

    status = models.CharField(
        max_length=20,
        choices=ENROLLMENT_STATUS_CHOICES,
        default="active",
        db_index=True,
    )

    completed_school_year = models.CharField(max_length=20, blank=True, default="")
    completed_calendar_year = models.IntegerField(null=True, blank=True)

    enrolled_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-enrolled_at"]

    def __str__(self):
        return f"{self.child} enrolled in {self.course}"

    def get_days_of_week_list(self):
        """Return days_of_week as a list of integers."""
        return list(self.days_of_week) if self.days_of_week else []

    def get_days_display(self):
        """Return human-readable day labels, e.g. 'Mon, Wed, Fri'."""
        day_map = dict(DAY_CHOICES)
        return ", ".join(day_map.get(d, str(d)) for d in self.days_of_week)


class CourseArchive(models.Model):
    """Immutable snapshot of a deleted course and its assignment history."""

    parent = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="course_archives"
    )
    original_course_id = models.IntegerField(db_index=True)
    course_name = models.CharField(max_length=200)
    remark = models.CharField(max_length=255, default="course deleted")
    archived_at = models.DateTimeField(auto_now_add=True)

    # Course metadata snapshot
    course_data = models.JSONField(default=dict)

    # Full history snapshots
    enrollment_history = models.JSONField(default=list)
    assignment_history = models.JSONField(default=list)

    class Meta:
        ordering = ["-archived_at"]

    def __str__(self):
        return f"{self.course_name} (archived)"
