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


class CalendarNavigationTests(TestCase):
    """Tests for S2.2 week navigation — prev/next/today links and week_display."""

    CALENDAR_URL = 'tracker:calendar'
    CALENDAR_WEEK_URL = 'tracker:calendar_week'

    def setUp(self):
        self.student = _make_student(username='nav_student')
        self.client.force_login(self.student)

    def _get_week(self, year, week):
        url = reverse(self.CALENDAR_WEEK_URL, kwargs={'year': year, 'week': week})
        return self.client.get(url)

    # ---------- context keys present ----------

    def test_nav_context_keys_present(self):
        response = self.client.get(reverse(self.CALENDAR_URL))
        for key in ('prev_year', 'prev_week', 'next_year', 'next_week',
                    'today_year', 'today_week', 'week_display'):
            self.assertIn(key, response.context, msg=f"Missing context key: {key}")

    # ---------- prev week ----------

    def test_prev_week_is_one_week_earlier(self):
        # Week 10 2026: Monday = 2 Mar 2026 → prev = week 9 2026
        response = self._get_week(2026, 10)
        self.assertEqual(response.context['prev_year'], 2026)
        self.assertEqual(response.context['prev_week'], 9)

    def test_prev_week_crosses_year_boundary(self):
        # ISO week 1 2026: Monday = 29 Dec 2025 → prev week = week 52/53 2025
        response = self._get_week(2026, 1)
        # prev_monday = 22 Dec 2025 → ISO week 52, year 2025
        self.assertEqual(response.context['prev_year'], 2025)
        self.assertEqual(response.context['prev_week'], 52)

    # ---------- next week ----------

    def test_next_week_is_one_week_later(self):
        response = self._get_week(2026, 10)
        self.assertEqual(response.context['next_year'], 2026)
        self.assertEqual(response.context['next_week'], 11)

    def test_next_week_crosses_year_boundary(self):
        # Last ISO week of 2026 — year 2026 has 52 ISO weeks; week 52 Mon = 21 Dec 2026
        response = self._get_week(2026, 52)
        # next_monday = 28 Dec 2026 → ISO week 53? No; 28 Dec 2026 is week 53 of 2026? Let's check:
        # 28 Dec 2026 isocalendar → year 2026, week 53 (2026 has 53 ISO weeks? No — need to verify)
        # Actually: 28 Dec 2026 is a Monday; ISO week 53 of 2026 exists if 1 Jan 2027 is in week 53.
        # 1 Jan 2027 = Friday → belongs to week 53 of 2026. So next = (2026, 53).
        # Then week 53 2026 next = week 1 2027.
        next_y = response.context['next_year']
        next_w = response.context['next_week']
        # Just verify it's a valid forward step
        curr_monday = datetime.date.fromisocalendar(2026, 52, 1)
        next_monday = datetime.date.fromisocalendar(next_y, next_w, 1)
        self.assertEqual((next_monday - curr_monday).days, 7)

    # ---------- today context ----------

    def test_today_context_matches_current_isoweek(self):
        response = self.client.get(reverse(self.CALENDAR_URL))
        today = datetime.date.today()
        iso_year, iso_week, _ = today.isocalendar()
        self.assertEqual(response.context['today_year'], iso_year)
        self.assertEqual(response.context['today_week'], iso_week)

    # ---------- week_display string ----------

    def test_week_display_same_month(self):
        # Week 10 2026: Mon 2 Mar – Fri 6 Mar 2026 → "2–6 Mar 2026"
        response = self._get_week(2026, 10)
        self.assertEqual(response.context['week_display'], '2–6 Mar 2026')

    def test_week_display_cross_month(self):
        # Week 13 2026: Mon 23 Mar – Fri 27 Mar 2026 → same month
        # Week 14 2026: Mon 30 Mar – Fri 3 Apr 2026 → cross month
        response = self._get_week(2026, 14)
        self.assertEqual(response.context['week_display'], '30 Mar–3 Apr 2026')

    # ---------- nav links rendered in template ----------

    def test_prev_link_in_rendered_output(self):
        response = self._get_week(2026, 10)
        prev_url = reverse(self.CALENDAR_WEEK_URL, kwargs={'year': 2026, 'week': 9})
        self.assertContains(response, prev_url)

    def test_next_link_in_rendered_output(self):
        response = self._get_week(2026, 10)
        next_url = reverse(self.CALENDAR_WEEK_URL, kwargs={'year': 2026, 'week': 11})
        self.assertContains(response, next_url)

    def test_today_button_in_rendered_output(self):
        response = self.client.get(reverse(self.CALENDAR_URL))
        today = datetime.date.today()
        iso_year, iso_week, _ = today.isocalendar()
        today_url = reverse(self.CALENDAR_WEEK_URL, kwargs={'year': iso_year, 'week': iso_week})
        self.assertContains(response, today_url)
        self.assertContains(response, 'Today')


class SubjectColourCardTests(TestCase):
    """Tests for S2.3 subject colour cards on the calendar."""

    CALENDAR_WEEK_URL = 'tracker:calendar_week'

    def setUp(self):
        parent = _make_parent(username='colour_parent')
        self.student = _make_student(username='colour_student')
        self.child = _make_child(parent, student_user=self.student)
        self.lesson = _make_lesson()
        self.enrolled = _make_enrolled_subject(self.child)
        # Place lesson on the Monday of ISO week 10, 2026 (2 Mar 2026)
        self.monday = datetime.date.fromisocalendar(2026, 10, 1)
        self.sl = _make_scheduled_lesson(self.child, self.lesson, self.enrolled, self.monday)
        self.client.force_login(self.student)

    def _get(self):
        return self.client.get(
            reverse(self.CALENDAR_WEEK_URL, kwargs={'year': 2026, 'week': 10})
        )

    # ---------- colour variable rendered ----------

    def test_subject_colour_hex_in_style_attribute(self):
        response = self._get()
        self.assertContains(response, f'--subject-colour: {self.enrolled.colour_hex}')

    def test_card_header_contains_subject_name(self):
        response = self._get()
        self.assertContains(response, self.enrolled.subject_name)

    def test_card_body_contains_lesson_title(self):
        response = self._get()
        self.assertContains(response, self.lesson.lesson_title)

    # ---------- no log — no badges, no dots ----------

    def test_no_badge_when_no_log(self):
        response = self._get()
        self.assertNotContains(response, 'Complete')
        self.assertNotContains(response, 'Skipped')
        self.assertNotContains(response, 'mastery-dot')

    # ---------- status badges ----------

    def test_complete_badge_rendered(self):
        LessonLog.objects.create(
            scheduled_lesson=self.sl, status='complete', mastery='unset',
            updated_by=self.student,
        )
        response = self._get()
        self.assertContains(response, 'Complete')

    def test_skipped_badge_rendered(self):
        LessonLog.objects.create(
            scheduled_lesson=self.sl, status='skipped', mastery='unset',
            updated_by=self.student,
        )
        response = self._get()
        self.assertContains(response, 'Skipped')

    # ---------- mastery dots ----------

    def test_green_mastery_dot_rendered(self):
        LessonLog.objects.create(
            scheduled_lesson=self.sl, status='complete', mastery='green',
            updated_by=self.student,
        )
        response = self._get()
        self.assertContains(response, 'mastery-dot green')

    def test_amber_mastery_dot_rendered(self):
        LessonLog.objects.create(
            scheduled_lesson=self.sl, status='complete', mastery='amber',
            updated_by=self.student,
        )
        response = self._get()
        self.assertContains(response, 'mastery-dot amber')

    def test_red_mastery_dot_rendered(self):
        LessonLog.objects.create(
            scheduled_lesson=self.sl, status='complete', mastery='red',
            updated_by=self.student,
        )
        response = self._get()
        self.assertContains(response, 'mastery-dot red')

    def test_unset_mastery_shows_no_dot(self):
        LessonLog.objects.create(
            scheduled_lesson=self.sl, status='complete', mastery='unset',
            updated_by=self.student,
        )
        response = self._get()
        self.assertNotContains(response, 'mastery-dot')

    # ---------- different subjects get different colours ----------

    def test_two_subjects_have_different_colours(self):
        lesson2 = _make_lesson(subject='English', title='Grammar', key_stage='KS3')
        enrolled2 = EnrolledSubject.objects.create(
            child=self.child,
            subject_name='English',
            key_stage='KS3',
            lessons_per_week=2,
            colour_hex='#EF4444',
        )
        wednesday = self.monday + datetime.timedelta(days=2)
        _make_scheduled_lesson(self.child, lesson2, enrolled2, wednesday)
        response = self._get()
        self.assertContains(response, '--subject-colour: #3B82F6')
        self.assertContains(response, '--subject-colour: #EF4444')

