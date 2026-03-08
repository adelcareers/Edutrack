"""Tests for the scheduler app — S1.4: Parent Creates Student Login."""

import datetime
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User

from accounts.models import UserProfile
from scheduler.models import Child


def _make_parent(username='parent1', password='TestPass123!'):
    """Helper: create a parent User + UserProfile."""
    user = User.objects.create_user(username=username, password=password)
    UserProfile.objects.create(user=user, role='parent')
    return user


def _make_child(parent, first_name='Alice'):
    """Helper: create a minimal Child record for a parent."""
    return Child.objects.create(
        parent=parent,
        first_name=first_name,
        birth_month=1,
        birth_year=2015,
        school_year='Year 5',
        academic_year_start=datetime.date(2025, 9, 1),
    )


CREATE_URL = 'scheduler:create_student_login'


class CreateStudentLoginAccessTests(TestCase):
    """Gate tests: who can reach the page."""

    def setUp(self):
        self.parent = _make_parent()
        self.child = _make_child(self.parent)
        self.url = reverse(CREATE_URL, kwargs={'child_id': self.child.pk})

    def test_unauthenticated_redirects_to_login(self):
        response = self.client.get(self.url)
        self.assertRedirects(response, f'/accounts/login/?next={self.url}')

    def test_student_role_blocked(self):
        student_user = User.objects.create_user(username='stu', password='Pass123!')
        UserProfile.objects.create(user=student_user, role='student')
        self.client.force_login(student_user)
        response = self.client.get(self.url)
        self.assertRedirects(response, '/')

    def test_parent_can_access_own_child(self):
        self.client.force_login(self.parent)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'scheduler/create_student_login.html')

    def test_parent_cannot_access_other_parents_child(self):
        other_parent = _make_parent(username='parent2')
        self.client.force_login(other_parent)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)


class CreateStudentLoginPostTests(TestCase):
    """Form submission scenarios."""

    def setUp(self):
        self.parent = _make_parent()
        self.child = _make_child(self.parent)
        self.url = reverse(CREATE_URL, kwargs={'child_id': self.child.pk})
        self.client.force_login(self.parent)

    def test_valid_post_creates_user_and_profile(self):
        response = self.client.post(self.url, {
            'username': 'alice_student',
            'password1': 'SecurePass99!',
            'password2': 'SecurePass99!',
        })
        self.assertRedirects(response, '/')
        student_user = User.objects.get(username='alice_student')
        self.assertEqual(student_user.profile.role, 'student')

    def test_valid_post_links_child_student_user(self):
        self.client.post(self.url, {
            'username': 'alice_student',
            'password1': 'SecurePass99!',
            'password2': 'SecurePass99!',
        })
        self.child.refresh_from_db()
        self.assertIsNotNone(self.child.student_user)
        self.assertEqual(self.child.student_user.username, 'alice_student')

    def test_duplicate_username_shows_error(self):
        User.objects.create_user(username='taken', password='Pass123!')
        response = self.client.post(self.url, {
            'username': 'taken',
            'password1': 'SecurePass99!',
            'password2': 'SecurePass99!',
        })
        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertTrue(form.errors)
        self.assertIn('username', form.errors)

    def test_mismatched_passwords_shows_error(self):
        response = self.client.post(self.url, {
            'username': 'alice_student',
            'password1': 'SecurePass99!',
            'password2': 'DifferentPass!',
        })
        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertIn('password2', form.errors)

    def test_child_with_existing_student_user_redirects(self):
        existing = User.objects.create_user(username='existing_stu', password='Pass123!')
        UserProfile.objects.create(user=existing, role='student')
        self.child.student_user = existing
        self.child.save()
        response = self.client.get(self.url)
        self.assertRedirects(response, '/')

    def test_student_can_log_in_after_creation(self):
        self.client.post(self.url, {
            'username': 'alice_student',
            'password1': 'SecurePass99!',
            'password2': 'SecurePass99!',
        })
        self.client.logout()
        logged_in = self.client.login(username='alice_student', password='SecurePass99!')
        self.assertTrue(logged_in)
