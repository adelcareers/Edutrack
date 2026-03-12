from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

try:
    from cloudinary.models import CloudinaryField
except ImportError:
    CloudinaryField = None  # fallback if cloudinary not installed in test env


GRADE_YEAR_CHOICES = [
    ('preschool', 'Preschool'),
    ('prek', 'Pre-K'),
    ('k', 'Kindergarten'),
    ('1', '1st Grade'),
    ('2', '2nd Grade'),
    ('3', '3rd Grade'),
    ('4', '4th Grade'),
    ('5', '5th Grade'),
    ('6', '6th Grade'),
    ('7', '7th Grade'),
    ('8', '8th Grade'),
    ('9', '9th Grade'),
    ('10', '10th Grade'),
    ('11', '11th Grade'),
    ('12', '12th Grade'),
]

GRADE_YEAR_LABELS = {k: v for k, v in GRADE_YEAR_CHOICES}

GRADING_STYLE_CHOICES = [
    ('not_graded', 'Not Graded'),
    ('point_graded', 'Point Graded'),
    ('percent_graded', 'Percent Graded'),
]

DEFAULT_ASSIGNMENT_TYPES = ['Homework', 'Quiz', 'Test', 'Paper', 'Lab', 'Other']


class Subject(models.Model):
    """A parent-scoped subject tag (e.g. "Maths", "English")."""

    parent = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='course_subjects'
    )
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ['name']
        unique_together = [('parent', 'name')]

    def __str__(self):
        return self.name


class Label(models.Model):
    """A parent-scoped coloured label for organising courses."""

    parent = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='course_labels'
    )
    name = models.CharField(max_length=100)
    color = models.CharField(max_length=7, default='#6c757d')

    class Meta:
        ordering = ['name']
        unique_together = [('parent', 'name')]

    def __str__(self):
        return self.name


class Course(models.Model):
    """A reusable course template created by a parent.

    A course has no fixed start / end date until a student is enrolled.
    It defines the structure (duration, frequency, grading) and can be
    enrolled for multiple students or reused across years.
    """

    parent = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='courses'
    )
    name = models.CharField(max_length=200)
    color = models.CharField(max_length=7, default='#6c757d')

    if CloudinaryField is not None:
        photo = CloudinaryField('course_photo', blank=True, null=True)
    else:
        photo = models.ImageField(upload_to='course_photos/', blank=True, null=True)

    subjects = models.ManyToManyField(Subject, blank=True, related_name='courses')
    labels = models.ManyToManyField(Label, blank=True, related_name='courses')

    # Grade years stored as a comma-separated string of GRADE_YEAR_CHOICES keys
    grade_years = models.CharField(max_length=200, blank=True, default='')

    duration_weeks = models.IntegerField(
        default=36,
        validators=[MinValueValidator(1), MaxValueValidator(52)],
    )
    frequency_days = models.IntegerField(
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(7)],
    )
    # Default days of week: Mon=0 … Sun=6 (CSV), used to pre-populate enrollment
    default_days = models.CharField(max_length=20, default='0,1,2,3,4')

    grading_style = models.CharField(
        max_length=20,
        choices=GRADING_STYLE_CHOICES,
        default='not_graded',
    )
    use_assignment_weights = models.BooleanField(default=False)
    credits = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)

    description = models.TextField(blank=True, default='')
    course_intro = models.TextField(blank=True, default='')

    is_archived = models.BooleanField(default=False, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    def get_grade_year_labels(self):
        """Return a list of human-readable grade year strings."""
        if not self.grade_years:
            return []
        return [GRADE_YEAR_LABELS.get(gy.strip(), gy.strip()) for gy in self.grade_years.split(',') if gy.strip()]

    def get_default_days_list(self):
        """Return default_days as a list of integers."""
        if not self.default_days:
            return []
        return [int(d) for d in self.default_days.split(',') if d.strip().isdigit()]

    @property
    def active_enrollments_count(self):
        return self.enrollments.filter(status='active').count()


class AssignmentType(models.Model):
    """An assignment category with an optional grade weight for a course."""

    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name='assignment_types'
    )
    name = models.CharField(max_length=100)
    weight = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ['order', 'name']

    def __str__(self):
        return f'{self.name} ({self.weight}%)'


ENROLLMENT_STATUS_CHOICES = [
    ('active', 'Active'),
    ('completed', 'Completed'),
    ('unenrolled', 'Unenrolled'),
]

DAY_CHOICES = [
    ('0', 'Mon'),
    ('1', 'Tue'),
    ('2', 'Wed'),
    ('3', 'Thu'),
    ('4', 'Fri'),
    ('5', 'Sat'),
    ('6', 'Sun'),
]


class CourseEnrollment(models.Model):
    """Links a Child to a Course for a specific start date and set of weekdays."""

    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name='enrollments'
    )
    child = models.ForeignKey(
        'scheduler.Child', on_delete=models.CASCADE, related_name='course_enrollments'
    )
    start_date = models.DateField()
    # CSV of chosen weekday ints, e.g. "0,2,4" for Mon/Wed/Fri
    days_of_week = models.CharField(max_length=20, default='0,1,2,3,4')

    status = models.CharField(
        max_length=20,
        choices=ENROLLMENT_STATUS_CHOICES,
        default='active',
        db_index=True,
    )

    completed_school_year = models.CharField(max_length=20, blank=True, default='')
    completed_calendar_year = models.IntegerField(null=True, blank=True)

    enrolled_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-enrolled_at']

    def __str__(self):
        return f'{self.child} enrolled in {self.course}'

    def get_days_of_week_list(self):
        """Return days_of_week as a list of integers."""
        if not self.days_of_week:
            return []
        return [int(d) for d in self.days_of_week.split(',') if d.strip().isdigit()]

    def get_days_display(self):
        """Return human-readable day labels, e.g. 'Mon, Wed, Fri'."""
        day_map = dict(DAY_CHOICES)
        return ', '.join(day_map.get(d.strip(), d) for d in self.days_of_week.split(',') if d.strip())
