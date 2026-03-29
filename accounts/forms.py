"""Forms for the accounts app."""

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User


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

    Students do not have an email address — they log in with a username
    and password chosen by their parent.
    """

    username = forms.CharField(
        max_length=150,
        help_text="The username your child will use to log in.",
    )
    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput,
    )

    def clean_username(self):
        """Ensure the username is not already taken."""
        username = self.cleaned_data.get("username", "").strip()
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("This username is already taken.")
        return username
