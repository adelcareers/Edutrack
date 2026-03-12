import datetime

from django import forms

from scheduler.models import Child

from .models import (
    Course,
    CourseEnrollment,
    GRADE_YEAR_CHOICES,
    Subject,
)

DAY_OF_WEEK_CHOICES = [
    ('0', 'Monday'),
    ('1', 'Tuesday'),
    ('2', 'Wednesday'),
    ('3', 'Thursday'),
    ('4', 'Friday'),
    ('5', 'Saturday'),
    ('6', 'Sunday'),
]

SCHOOL_YEAR_CHOICES = [
    ('2023-2024', '2023-2024'),
    ('2024-2025', '2024-2025'),
    ('2025-2026', '2025-2026'),
    ('2026-2027', '2026-2027'),
]


class CourseForm(forms.ModelForm):
    """Form for creating and editing a Course."""

    grade_years_list = forms.MultipleChoiceField(
        choices=GRADE_YEAR_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label='Grade Year(s)',
    )

    class Meta:
        model = Course
        fields = [
            'name', 'color', 'duration_weeks', 'frequency_days',
            'grading_style', 'use_assignment_weights', 'credits',
            'description', 'course_intro',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Course Name'}),
            'color': forms.TextInput(attrs={'type': 'color', 'class': 'form-control form-control-color'}),
            'duration_weeks': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 52}),
            'frequency_days': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 7}),
            'grading_style': forms.Select(attrs={'class': 'form-select'}),
            'use_assignment_weights': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'credits': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.5', 'min': 0}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            'course_intro': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # Populate grade_years_list from instance.grade_years CSV
        if self.instance and self.instance.grade_years:
            self.fields['grade_years_list'].initial = [
                g.strip() for g in self.instance.grade_years.split(',') if g.strip()
            ]

    def save(self, commit=True):
        course = super().save(commit=False)
        # Convert grade_years_list → CSV string
        grade_years = self.cleaned_data.get('grade_years_list', [])
        course.grade_years = ','.join(grade_years)
        if commit:
            course.save()
            self._save_m2m()
        return course


class SubjectForm(forms.ModelForm):
    class Meta:
        model = Subject
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Subject name'}),
        }


class EnrollStudentForm(forms.ModelForm):
    """Form to enroll a student in a course."""

    days_of_week = forms.MultipleChoiceField(
        choices=DAY_OF_WEEK_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        label='Days of Week',
    )

    class Meta:
        model = CourseEnrollment
        fields = ['child', 'start_date', 'days_of_week']
        widgets = {
            'child': forms.Select(attrs={'class': 'form-select'}),
            'start_date': forms.DateInput(
                attrs={'class': 'form-control', 'type': 'date'},
                format='%Y-%m-%d',
            ),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        self.course = kwargs.pop('course')
        super().__init__(*args, **kwargs)

        # Filter children to those owned by the parent
        self.fields['child'].queryset = Child.objects.filter(
            parent=self.user, is_active=True
        )
        self.fields['child'].empty_label = '— Select a student —'

        # Set today as default start date
        self.fields['start_date'].initial = datetime.date.today().strftime('%Y-%m-%d')

        # Pre-select default days from course
        if self.course:
            default_days = [str(d) for d in self.course.get_default_days_list()]
            self.fields['days_of_week'].initial = default_days

    def clean_days_of_week(self):
        days = self.cleaned_data.get('days_of_week', [])
        if len(days) != self.course.frequency_days:
            raise forms.ValidationError(
                f'This course requires exactly {self.course.frequency_days} '
                f'day(s) per week. You selected {len(days)}.'
            )
        return days


class CompleteEnrollmentForm(forms.Form):
    """Form to mark a student's course enrollment as complete."""

    completed_school_year = forms.ChoiceField(
        choices=SCHOOL_YEAR_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='School Year',
    )
    completed_calendar_year = forms.IntegerField(
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 2000, 'max': 2100}),
        label='Calendar Year',
        initial=datetime.date.today().year,
    )
