"""Tests for the reports app — S3.1 Report Creation Form."""

import datetime

from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User

from accounts.models import UserProfile
from reports.forms import ReportForm
from reports.models import Report
from scheduler.models import Child, EnrolledSubject, ScheduledLesson
from tracker.models import LessonLog


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_parent(username='rpt_parent', password='TestPass123!'):
    user = User.objects.create_user(username=username, password=password)
    UserProfile.objects.create(user=user, role='parent')
    return user


def _make_student(username='rpt_student', password='TestPass123!'):
    user = User.objects.create_user(username=username, password=password)
    UserProfile.objects.create(user=user, role='student')
    return user


def _make_child(parent, first_name='Alex'):
    return Child.objects.create(
        parent=parent,
        first_name=first_name,
        birth_month=4,
        birth_year=2013,
        school_year='Year 8',
        academic_year_start=datetime.date(2025, 9, 1),
    )


# ---------------------------------------------------------------------------
# S3.1 / T1 — ReportForm
# ---------------------------------------------------------------------------

class ReportFormValidationTests(TestCase):
    """Tests for ReportForm date range validation."""

    def _form(self, date_from, date_to, report_type='summary'):
        return ReportForm(data={
            'date_from': date_from,
            'date_to': date_to,
            'report_type': report_type,
        })

    def test_valid_date_range_is_valid(self):
        form = self._form('2026-01-01', '2026-03-31')
        self.assertTrue(form.is_valid())

    def test_date_from_equal_to_date_to_is_invalid(self):
        form = self._form('2026-01-01', '2026-01-01')
        self.assertFalse(form.is_valid())

    def test_date_from_after_date_to_is_invalid(self):
        form = self._form('2026-04-01', '2026-01-01')
        self.assertFalse(form.is_valid())

    def test_invalid_date_range_contains_error_message(self):
        form = self._form('2026-04-01', '2026-01-01')
        form.is_valid()
        self.assertIn('Start date must be before end date.', form.non_field_errors())

    def test_summary_type_is_valid(self):
        form = self._form('2026-01-01', '2026-06-30', report_type='summary')
        self.assertTrue(form.is_valid())

    def test_portfolio_type_is_valid(self):
        form = self._form('2026-01-01', '2026-06-30', report_type='portfolio')
        self.assertTrue(form.is_valid())

    def test_invalid_report_type_rejected(self):
        form = self._form('2026-01-01', '2026-06-30', report_type='invalid_type')
        self.assertFalse(form.is_valid())

    def test_missing_date_from_is_invalid(self):
        form = ReportForm(data={'date_to': '2026-06-30', 'report_type': 'summary'})
        self.assertFalse(form.is_valid())

    def test_missing_date_to_is_invalid(self):
        form = ReportForm(data={'date_from': '2026-01-01', 'report_type': 'summary'})
        self.assertFalse(form.is_valid())


# ---------------------------------------------------------------------------
# S3.1 / T2+T4 — create_report_view
# ---------------------------------------------------------------------------

class CreateReportViewTests(TestCase):
    """Tests for create_report_view access control and behaviour."""

    CREATE_URL = 'reports:create_report'

    def setUp(self):
        self.parent = _make_parent()
        self.child = _make_child(self.parent)
        self.student = _make_student()

    def _url(self, child_id=None):
        return reverse(self.CREATE_URL, kwargs={'child_id': child_id or self.child.pk})

    def _post(self, date_from='2026-01-01', date_to='2026-06-30', report_type='summary', child_id=None):
        return self.client.post(self._url(child_id), {
            'date_from': date_from,
            'date_to': date_to,
            'report_type': report_type,
        })

    # ---------- access ----------

    def test_unauthenticated_redirects(self):
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 302)

    def test_student_role_blocked(self):
        self.client.force_login(self.student)
        response = self.client.get(self._url())
        self.assertRedirects(response, '/', fetch_redirect_response=False)

    def test_other_parent_gets_404(self):
        other = _make_parent(username='rpt_other_parent')
        self.client.force_login(other)
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 404)

    def test_owner_parent_gets_200(self):
        self.client.force_login(self.parent)
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)

    # ---------- GET rendering ----------

    def test_get_uses_correct_template(self):
        self.client.force_login(self.parent)
        response = self.client.get(self._url())
        self.assertTemplateUsed(response, 'reports/create_report.html')

    def test_get_passes_form_to_context(self):
        self.client.force_login(self.parent)
        response = self.client.get(self._url())
        self.assertIsInstance(response.context['form'], ReportForm)

    def test_get_passes_child_to_context(self):
        self.client.force_login(self.parent)
        response = self.client.get(self._url())
        self.assertEqual(response.context['child'], self.child)

    def test_get_passes_total_completed_to_context(self):
        self.client.force_login(self.parent)
        response = self.client.get(self._url())
        self.assertIn('total_completed', response.context)

    def test_total_completed_reflects_lesson_logs(self):
        # Create a completed LessonLog for the child
        from curriculum.models import Lesson
        lesson = Lesson.objects.create(
            key_stage='KS3', subject_name='Maths',
            unit_title='Numbers', lesson_number=1, lesson_title='Counting',
            lesson_url='http://example.com',
        )
        enrolled = EnrolledSubject.objects.create(
            child=self.child, subject_name='Maths', key_stage='KS3',
            lessons_per_week=2, colour_hex='#123456',
        )
        sl = ScheduledLesson.objects.create(
            child=self.child, lesson=lesson, enrolled_subject=enrolled,
            scheduled_date=datetime.date(2026, 2, 1),
        )
        LessonLog.objects.create(scheduled_lesson=sl, status='complete')

        self.client.force_login(self.parent)
        response = self.client.get(self._url())
        self.assertEqual(response.context['total_completed'], 1)

    # ---------- POST valid ----------

    def test_valid_post_creates_report(self):
        self.client.force_login(self.parent)
        self._post()
        self.assertEqual(Report.objects.filter(child=self.child).count(), 1)

    def test_valid_post_sets_child_on_report(self):
        self.client.force_login(self.parent)
        self._post()
        report = Report.objects.get(child=self.child)
        self.assertEqual(report.child, self.child)

    def test_valid_post_sets_created_by(self):
        self.client.force_login(self.parent)
        self._post()
        report = Report.objects.get(child=self.child)
        self.assertEqual(report.created_by, self.parent)

    def test_valid_post_redirects(self):
        self.client.force_login(self.parent)
        response = self._post()
        self.assertEqual(response.status_code, 302)

    def test_valid_post_redirects_to_dashboard(self):
        self.client.force_login(self.parent)
        response = self._post()
        self.assertRedirects(response, reverse('scheduler:parent_dashboard'),
                             fetch_redirect_response=False)

    # ---------- POST invalid ----------

    def test_invalid_date_range_rerenders_form(self):
        self.client.force_login(self.parent)
        response = self._post(date_from='2026-06-30', date_to='2026-01-01')
        self.assertEqual(response.status_code, 200)

    def test_invalid_date_range_shows_error(self):
        self.client.force_login(self.parent)
        response = self._post(date_from='2026-06-30', date_to='2026-01-01')
        self.assertContains(response, 'Start date must be before end date.')

    def test_invalid_post_does_not_create_report(self):
        self.client.force_login(self.parent)
        self._post(date_from='2026-06-30', date_to='2026-01-01')
        self.assertEqual(Report.objects.filter(child=self.child).count(), 0)

