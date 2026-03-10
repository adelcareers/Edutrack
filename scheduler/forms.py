"""Forms for the scheduler app."""

import datetime
from django import forms

from curriculum.models import Lesson
from scheduler.models import Child


MONTH_CHOICES = [
    (1, 'January'), (2, 'February'), (3, 'March'), (4, 'April'),
    (5, 'May'), (6, 'June'), (7, 'July'), (8, 'August'),
    (9, 'September'), (10, 'October'), (11, 'November'), (12, 'December'),
]


class ChildForm(forms.ModelForm):
    """Form for a parent to add a child's profile.

    The ``school_year`` field is populated dynamically from distinct year
    values in the curriculum ``Lesson`` table, so the choices always reflect
    the available curriculum data rather than a hardcoded list.
    """

    birth_month = forms.TypedChoiceField(choices=MONTH_CHOICES, coerce=int)
    school_year = forms.ChoiceField(choices=[])

    class Meta:
        model = Child
        fields = ['first_name', 'birth_month', 'birth_year', 'school_year', 'academic_year_start']
        widgets = {
            'birth_year': forms.NumberInput(
                attrs={'min': 2000, 'max': datetime.date.today().year}
            ),
            'academic_year_start': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        years = sorted(Lesson.objects.values_list('year', flat=True).distinct())
        self.fields['school_year'].choices = (
            [('', '--- Select year group ---')] + [(y, y) for y in years]
        )


class NewStudentModalForm(forms.Form):
    """Simplified form used in the 'New Student' modal on the child list page.

    Only exposes the fields shown in the UI: name, optional school year, and
    an optional photo.  Other Child fields (birth details, academic year start)
    are defaulted automatically in the view.
    """

    first_name = forms.CharField(
        max_length=100,
        label='Student Name',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter student name',
            'autofocus': True,
        }),
    )
    school_year = forms.ChoiceField(
        label='School Year',
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    photo = forms.ImageField(
        required=False,
        label='Photo',
        widget=forms.FileInput(attrs={'class': 'd-none', 'accept': 'image/*', 'id': 'id_photo'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        years = sorted(Lesson.objects.values_list('year', flat=True).distinct())
        self.fields['school_year'].choices = (
            [('', '— optional —')] + [(y, y) for y in years]
        )
