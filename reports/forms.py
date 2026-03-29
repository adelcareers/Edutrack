import datetime

from django import forms

from reports.models import Report


class ReportForm(forms.ModelForm):
    """Form for creating a progress report.

    Parents select a date range and report type. The clean() method
    validates that date_from is strictly before date_to.
    """

    date_from = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        label="From",
    )
    date_to = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        label="To",
    )
    report_type = forms.ChoiceField(
        choices=Report.TYPE_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Report Type",
    )

    class Meta:
        model = Report
        fields = ["date_from", "date_to", "report_type"]

    def clean(self):
        cleaned = super().clean()
        date_from = cleaned.get("date_from")
        date_to = cleaned.get("date_to")
        if date_from and date_to and date_from >= date_to:
            raise forms.ValidationError("Start date must be before end date.")
        return cleaned
