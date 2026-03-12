import datetime

from django import forms

from scheduler.models import Child

from .models import (
    Course,
    CourseEnrollment,
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
    ('', '— Select year —'),
    ('year1',  'Year 1'),
    ('year2',  'Year 2'),
    ('year3',  'Year 3'),
    ('year4',  'Year 4'),
    ('year5',  'Year 5'),
    ('year6',  'Year 6'),
    ('year7',  'Year 7'),
    ('year8',  'Year 8'),
    ('year9',  'Year 9'),
    ('year10', 'Year 10'),
    ('year11', 'Year 11'),
    ('all',    'All Years'),
]


class CourseForm(forms.ModelForm):
    """Form for creating and editing a Course."""

    grade_years_list = forms.ChoiceField(
        choices=SCHOOL_YEAR_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='School Year',
    )

    class Meta:
        model = Course
        fields = [
            'name', 'color', 'labels', 'duration_weeks', 'frequency_days',
            'grading_style', 'use_assignment_weights', 'credits',
            'description', 'course_intro',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Course Name'}),
            'color': forms.TextInput(attrs={'type': 'color', 'class': 'form-control form-control-color'}),
            'labels': forms.SelectMultiple(attrs={'class': 'form-select select2-labels'}),
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

        # Populate grade_years_list from instance.grade_years (single value)
        if self.instance and self.instance.grade_years:
            first = self.instance.grade_years.split(',')[0].strip()
            self.fields['grade_years_list'].initial = first

    def save(self, commit=True):
        course = super().save(commit=False)
        # Store single school year selection
        grade_year = self.cleaned_data.get('grade_years_list', '')
        course.grade_years = grade_year or ''
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
