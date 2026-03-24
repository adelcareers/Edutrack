"""Tests for the accounts app — registration, login, and role-based access."""

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from .decorators import role_required
from .models import ParentSettings, UserProfile


def make_user(username, role):
    """Helper: create a User + UserProfile with the given role."""
    user = User.objects.create_user(username=username, password="testpass123")
    UserProfile.objects.create(user=user, role=role)
    return user


# ── Registration ──────────────────────────────────────────────────────────────


class RegistrationTests(TestCase):
    """Tests for the parent registration view."""

    def test_register_get_returns_200(self):
        response = self.client.get(reverse("accounts:register"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/register.html")

    def test_registration_creates_parent_role(self):
        response = self.client.post(
            reverse("accounts:register"),
            {
                "first_name": "Alice",
                "last_name": "Smith",
                "email": "alice@example.com",
                "password1": "Str0ng!Pass99",
                "password2": "Str0ng!Pass99",
            },
        )
        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)
        user = User.objects.get(email="alice@example.com")
        self.assertEqual(user.username, "alice@example.com")
        self.assertEqual(user.profile.role, "parent")

    def test_register_duplicate_email_shows_error(self):
        User.objects.create_user(
            username="existing@example.com", email="existing@example.com", password="x"
        )
        response = self.client.post(
            reverse("accounts:register"),
            {
                "first_name": "Bob",
                "last_name": "Jones",
                "email": "existing@example.com",
                "password1": "Str0ng!Pass99",
                "password2": "Str0ng!Pass99",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"],
            "email",
            "An account with this email already exists.",
        )

    def test_register_mismatched_passwords_shows_error(self):
        response = self.client.post(
            reverse("accounts:register"),
            {
                "first_name": "Carol",
                "last_name": "White",
                "email": "carol@example.com",
                "password1": "Str0ng!Pass99",
                "password2": "Different!Pass99",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"],
            "password2",
            "The two password fields didn\u2019t match.",
        )


# ── Login / Logout ────────────────────────────────────────────────────────────


class LoginLogoutTests(TestCase):
    """Tests for login and logout views."""

    def setUp(self):
        self.parent = make_user("parent@example.com", "parent")
        self.parent.set_password("Str0ng!Pass99")
        self.parent.save()

    def test_login_valid_credentials_redirects_home(self):
        response = self.client.post(
            reverse("accounts:login"),
            {
                "username": "parent@example.com",
                "password": "Str0ng!Pass99",
            },
        )
        self.assertRedirects(response, "/", fetch_redirect_response=False)

    def test_login_wrong_password_shows_error(self):
        response = self.client.post(
            reverse("accounts:login"),
            {
                "username": "parent@example.com",
                "password": "wrongpassword",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please enter a correct")

    def test_logout_post_clears_session(self):
        self.client.login(username="parent@example.com", password="Str0ng!Pass99")
        response = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(response, "/")
        # Subsequent request to a login-required URL should redirect to login
        self.assertFalse(response.wsgi_request.user.is_authenticated)


# ── role_required decorator ───────────────────────────────────────────────────


class RoleRequiredDecoratorTests(TestCase):
    """Tests for the role_required decorator — the core RBAC primitive."""

    def setUp(self):
        self.parent = make_user("parent_user", "parent")
        self.student = make_user("student_user", "student")

        # Create a minimal protected view for testing
        from django.http import HttpResponse

        @role_required("parent")
        def parent_only_view(request):
            return HttpResponse("parent content")

        @role_required("student")
        def student_only_view(request):
            return HttpResponse("student content")

        self.parent_only_view = parent_only_view
        self.student_only_view = student_only_view

    def test_unauthenticated_redirects_to_login(self):
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.test import RequestFactory

        rf = RequestFactory()
        request = rf.get("/fake-parent-url/")
        request.user = type("AnonymousUser", (), {"is_authenticated": False})()
        # Attach message storage
        setattr(request, "session", {})
        messages_storage = FallbackStorage(request)
        setattr(request, "_messages", messages_storage)
        response = self.parent_only_view(request)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_correct_role_allows_access(self):
        self.client.force_login(self.parent)
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.test import RequestFactory

        rf = RequestFactory()
        request = rf.get("/fake-parent-url/")
        request.user = self.parent
        setattr(request, "session", {})
        setattr(request, "_messages", FallbackStorage(request))
        response = self.parent_only_view(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"parent content")

    def test_parent_blocked_from_student_views(self):
        self.client.force_login(self.parent)
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.test import RequestFactory

        rf = RequestFactory()
        request = rf.get("/fake-student-url/")
        request.user = self.parent
        setattr(request, "session", {})
        setattr(request, "_messages", FallbackStorage(request))
        response = self.student_only_view(request)
        self.assertEqual(response.status_code, 302)

    def test_student_blocked_from_parent_views(self):
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.test import RequestFactory

        rf = RequestFactory()
        request = rf.get("/fake-parent-url/")
        request.user = self.student
        setattr(request, "session", {})
        setattr(request, "_messages", FallbackStorage(request))
        response = self.parent_only_view(request)
        self.assertEqual(response.status_code, 302)

    def test_decorator_preserves_function_name(self):
        from django.http import HttpResponse

        @role_required("parent")
        def my_named_view(request):
            return HttpResponse("ok")

        self.assertEqual(my_named_view.__name__, "my_named_view")


class ParentSettingsTests(TestCase):
    """Tests for parent settings persistence."""

    def setUp(self):
        self.parent = make_user("settings_parent", "parent")
        self.client = Client()
        self.client.force_login(self.parent)

    def test_settings_page_renders_receipt_mode_control(self):
        response = self.client.get(reverse("accounts:settings"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Lesson Receipt Link Policy")

    def test_settings_saves_receipt_enforcement_mode(self):
        response = self.client.post(
            reverse("accounts:settings"),
            {
                "first_day_of_week": "0",
                "receipt_enforcement_mode": "hard",
            },
        )
        self.assertEqual(response.status_code, 302)
        settings = ParentSettings.objects.get(user=self.parent)
        self.assertEqual(settings.receipt_enforcement_mode, "hard")
