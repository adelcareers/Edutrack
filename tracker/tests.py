"""Tests for the tracker app — S2.1 Weekly Calendar View."""

import datetime

from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User

from accounts.models import UserProfile
from curriculum.models import Lesson
from scheduler.models import Child, EnrolledSubject, ScheduledLesson
from tracker.models import LessonLog


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_parent(username='cal_parent', password='TestPass123!'):
    user = User.objects.create_user(username=username, password=password)
    UserProfile.objects.create(user=user, role='parent')
    return user


def _make_student(username='cal_student', password='TestPass123!'):
    user = User.objects.create_user(username=username, password=password)
    UserProfile.objects.create(user=user, role='student')
    return user


def _make_child(parent, student_user=None, first_name='Sam'):
    return Child.objects.create(
        parent=parent,
        first_name=first_name,
        birth_month=3,
        birth_year=2014,
        school_year='Year 7',
        academic_year_start=datetime.date(2025, 9, 1),
        student_user=student_user,
    )


def _make_lesson(subject='Maths', title='Counting', key_stage='KS3'):
    return Lesson.objects.create(
        key_stage=key_stage,
        subject_name=subject,
        programme_slug='maths-ks3',
        year='Year 7',
        unit_slug='number',
        unit_title='Number',
        lesson_number=1,
        lesson_title=title,
        lesson_url='https://example.com/lesson',
    )


def _make_enrolled_subject(child, subject_name='Maths'):
    return EnrolledSubject.objects.create(
        child=child,
        subject_name=subject_name,
        key_stage='KS3',
        lessons_per_week=2,
        colour_hex='#3B82F6',
    )


def _make_scheduled_lesson(child, lesson, enrolled_subject, date):
    return ScheduledLesson.objects.create(
        child=child,
        lesson=lesson,
        enrolled_subject=enrolled_subject,
        scheduled_date=date,
        order_on_day=0,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class CalendarViewTests(TestCase):
    """Tests for calendar_view (S2.1)."""

    CALENDAR_URL = 'tracker:calendar'
    CALENDAR_WEEK_URL = 'tracker:calendar_week'

    def setUp(self):
        self.parent = _make_parent()
        self.student = _make_student()
        self.child = _make_child(self.parent, student_user=self.student)
        self.url = reverse(self.CALENDAR_URL)

    # ---------- access ----------

    def test_unauthenticated_redirects_to_login(self):
        response = self.client.get(self.url)
        self.assertRedirects(response, f'/accounts/login/?next={self.url}')

    def test_parent_role_blocked(self):
        self.client.force_login(self.parent)
        response = self.client.get(self.url)
        self.assertRedirects(response, '/', fetch_redirect_response=False)

    # ---------- GET returns 200 ----------

    def test_student_gets_200(self):
        self.client.force_login(self.student)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_uses_calendar_template(self):
        self.client.force_login(self.student)
        response = self.client.get(self.url)
        self.assertTemplateUsed(response, 'tracker/calendar.html')

    # ---------- context ----------

    def test_context_has_required_keys(self):
        self.client.force_login(self.student)
        response = self.client.get(self.url)
        for key in ('days', 'year', 'week', 'today'):
            self.assertIn(key, response.context)

    def test_days_has_five_columns(self):
        self.client.force_login(self.student)
        response = self.client.get(self.url)
        days = response.context['days']
        self.assertEqual(len(days), 5)
        for name in ('monday', 'tuesday', 'wednesday', 'thursday', 'friday'):
            self.assertIn(name, days)

    def test_default_week_matches_today(self):
        self.client.force_login(self.student)
        response = self.client.get(self.url)
        today = datetime.date.today()
        iso_year, iso_week, _ = today.isocalendar()
        self.assertEqual(response.context['year'], iso_year)
        self.assertEqual(response.context['week'], iso_week)

    # ---------- specific week URL ----------

    def test_specific_week_url_sets_context(self):
        self.client.force_login(self.student)
        url = reverse(self.CALENDAR_WEEK_URL, kwargs={'year': 2025, 'week': 1})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['year'], 2025)
        self.assertEqual(response.context['week'], 1)

    # ---------- lessons in correct day ----------

    def test_lesson_appears_in_correct_day(self):
        # ISO week 1, 2025 starts Monday 30 Dec 2024
        monday = datetime.date.fromisocalendar(2025, 1, 1)  # Monday
        lesson = _make_lesson()
        enrolled = _make_enrolled_subject(self.child)
        _make_scheduled_lesson(self.child, lesson, enrolled, monday)

        self.client.force_login(self.student)
        url = reverse(self.CALENDAR_WEEK_URL, kwargs={'year': 2025, 'week': 1})
        response = self.client.get(url)
        monday_lessons = response.context['days']['monday']['lessons']
        self.assertEqual(len(monday_lessons), 1)
        self.assertEqual(monday_lessons[0].lesson.lesson_title, 'Counting')

    def test_lesson_on_wednesday_not_in_monday(self):
        wednesday = datetime.date.fromisocalendar(2025, 1, 3)
        lesson = _make_lesson()
        enrolled = _make_enrolled_subject(self.child)
        _make_scheduled_lesson(self.child, lesson, enrolled, wednesday)

        self.client.force_login(self.student)
        url = reverse(self.CALENDAR_WEEK_URL, kwargs={'year': 2025, 'week': 1})
        response = self.client.get(url)
        self.assertEqual(len(response.context['days']['monday']['lessons']), 0)
        self.assertEqual(len(response.context['days']['wednesday']['lessons']), 1)

    # ---------- empty day ----------

    def test_empty_day_has_no_lessons(self):
        self.client.force_login(self.student)
        response = self.client.get(self.url)
        for name, day in response.context['days'].items():
            self.assertEqual(day['lessons'], [])

    def test_empty_day_renders_no_lessons_message(self):
        self.client.force_login(self.student)
        response = self.client.get(self.url)
        self.assertContains(response, 'No lessons scheduled')

    # ---------- student without child_profile ----------

    def test_student_without_child_profile_gets_200(self):
        orphan = User.objects.create_user(username='orphan_stu', password='Pass123!')
        UserProfile.objects.create(user=orphan, role='student')
        self.client.force_login(orphan)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        for name, day in response.context['days'].items():
            self.assertEqual(day['lessons'], [])

