"""Forms for the accounts app."""

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError


class CustomUserCreationForm(UserCreationForm):
    """Registration form for new parent accounts.

    Uses email as the primary identifier. The email is validated for
    uniqueness and is copied to the username field on save so Django's
    built-in auth machinery continues to work without modification.
    """

    email = forms.EmailField(
        required=True,
        help_text="Required. A confirmation will be sent to this address.",
    )
    first_name = forms.CharField(max_length=150, required=True)
    last_name = forms.CharField(max_length=150, required=True)

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "password1", "password2")

    def clean_email(self):
        """Ensure the email address is not already registered."""
        email = self.cleaned_data.get("email", "").lower().strip()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def save(self, commit=True):
        """Save the user with username set to the normalised email address."""
        user = super().save(commit=False)
        email = self.cleaned_data["email"].lower().strip()
        user.username = email
        user.email = email
        user.first_name = self.cleaned_data["first_name"].strip()
        user.last_name = self.cleaned_data["last_name"].strip()
        if commit:
            user.save()
        return user


class StudentCreationForm(forms.Form):
    """Form for a parent to create login credentials for their child.

    Students log in with an email address chosen by their parent. For MVP this
    email is also stored in Django's ``username`` field so the existing auth
    backend does not need to change.
    """

    email = forms.EmailField(
        help_text="The email your child will use to log in.",
    )
    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput,
    )
    password2 = forms.CharField(
        label="Confirm password",
        widget=forms.PasswordInput,
    )

    def clean_email(self):
        """Ensure the email address is globally unique across auth users."""
        email = self.cleaned_data.get("email", "").lower().strip()
        if (
            User.objects.filter(username__iexact=email).exists()
            or User.objects.filter(email__iexact=email).exists()
        ):
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1", "")
        password2 = cleaned_data.get("password2", "")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "Passwords do not match.")
        if password1:
            try:
                validate_password(password1)
            except ValidationError as exc:
                self.add_error("password1", exc)
        return cleaned_data
