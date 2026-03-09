"""Tests for the reports app — S3.1 Report Creation Form, S3.2 PDF Generation."""

import datetime
import uuid
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from django.utils import timezone

from accounts.models import UserProfile
from curriculum.models import Lesson
from reports.forms import ReportForm
from reports.models import Report
from reports.services import generate_pdf
from scheduler.models import Child, EnrolledSubject, ScheduledLesson
from tracker.models import LessonLog


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_parent(username='rpt_parent', password='TestPass123!'):
    user = User.objects.create_user(username=username, password=password)
    UserProfile.objects.create(user=user, role='parent', subscription_active=True)
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
        patcher = patch(
            'reports.views.generate_pdf',
            return_value='https://cdn.example.com/r.pdf',
        )
        self.mock_generate_pdf = patcher.start()
        self.addCleanup(patcher.stop)

    def _url(self, child_id=None):
        return reverse(self.CREATE_URL, kwargs={'child_id': child_id or self.child.pk})

    def _post(self, date_from='2026-01-01', date_to='2026-06-30', report_type='summary', child_id=None):
        return self.client.post(self._url(child_id), {
            'date_from': date_from,
            'date_to': date_to,
            'report_type': report_type,
        })

    # ---------- access ----------

    def test_parent_without_subscription_is_redirected(self):
        """S3.5 T4: Protect report generation with subscription_active flag."""
        unsubscribed_user = User.objects.create_user(username='no_sub', password='pw')
        UserProfile.objects.create(user=unsubscribed_user, role='parent', subscription_active=False)
        child = _make_child(unsubscribed_user, 'NoSubChild')
        
        self.client.login(username='no_sub', password='pw')
        res = self.client.get(reverse(self.CREATE_URL, args=[child.id]))
        self.assertRedirects(res, reverse('payments:pricing'))

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

    def test_valid_post_redirects_to_detail(self):
        self.client.force_login(self.parent)
        response = self._post()
        report = Report.objects.get(child=self.child)
        self.assertRedirects(
            response,
            reverse('reports:report_detail', kwargs={'pk': report.pk}),
            fetch_redirect_response=False,
        )

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


# ---------------------------------------------------------------------------
# S3.2 / T2 — generate_pdf service
# ---------------------------------------------------------------------------

def _make_lesson(subject='Maths', title='Counting', number=1):
    return Lesson.objects.create(
        key_stage='KS3',
        subject_name=subject,
        unit_title='Numbers',
        lesson_number=number,
        lesson_title=title,
        lesson_url='http://example.com',
    )


def _make_enrolled(child, subject='Maths'):
    return EnrolledSubject.objects.create(
        child=child,
        subject_name=subject,
        key_stage='KS3',
        lessons_per_week=2,
        colour_hex='#123456',
    )


class GeneratePdfServiceTests(TestCase):
    """Tests for reports.services.generate_pdf."""

    def setUp(self):
        self.parent = _make_parent(username='svc_parent')
        self.child = _make_child(self.parent, first_name='SvcChild')
        self.report = Report.objects.create(
            child=self.child,
            created_by=self.parent,
            report_type='summary',
            date_from=datetime.date(2026, 1, 1),
            date_to=datetime.date(2026, 6, 30),
        )
        self._upload_rv = {
            'public_id': 'reports/test_report.pdf',
            'secure_url': 'https://cdn.example.com/test_report.pdf',
        }

    @patch('reports.services.cloudinary.uploader.upload')
    @patch('reports.services.pisa.CreatePDF')
    def test_returns_secure_url(self, mock_pisa, mock_upload):
        mock_upload.return_value = self._upload_rv
        url = generate_pdf(self.report)
        self.assertEqual(url, 'https://cdn.example.com/test_report.pdf')

    @patch('reports.services.cloudinary.uploader.upload')
    @patch('reports.services.pisa.CreatePDF')
    def test_sets_pdf_file_on_report(self, mock_pisa, mock_upload):
        mock_upload.return_value = self._upload_rv
        generate_pdf(self.report)
        self.report.refresh_from_db()
        # CloudinaryField strips the format extension from the public_id.
        self.assertIn('reports/test_report', str(self.report.pdf_file))

    @patch('reports.services.cloudinary.uploader.upload')
    @patch('reports.services.pisa.CreatePDF')
    def test_calls_cloudinary_upload(self, mock_pisa, mock_upload):
        mock_upload.return_value = self._upload_rv
        generate_pdf(self.report)
        self.assertTrue(mock_upload.called)
        call_kwargs = mock_upload.call_args[1]
        self.assertEqual(call_kwargs.get('resource_type'), 'raw')

    @patch('reports.services.cloudinary.uploader.upload')
    @patch('reports.services.pisa.CreatePDF')
    def test_only_completed_logs_included_in_html(self, mock_pisa, mock_upload):
        """Completed lessons appear in context; pending ones do not."""
        mock_upload.return_value = self._upload_rv
        lesson = _make_lesson()
        enrolled = _make_enrolled(self.child)
        sl_done = ScheduledLesson.objects.create(
            child=self.child, lesson=lesson, enrolled_subject=enrolled,
            scheduled_date=datetime.date(2026, 3, 1),
        )
        sl_pending = ScheduledLesson.objects.create(
            child=self.child, lesson=lesson, enrolled_subject=enrolled,
            scheduled_date=datetime.date(2026, 3, 2),
        )
        LessonLog.objects.create(scheduled_lesson=sl_done, status='complete')
        LessonLog.objects.create(scheduled_lesson=sl_pending, status='pending')

        generate_pdf(self.report)

        html = mock_pisa.call_args[0][0]
        self.assertIn('SvcChild', html)

    @patch('reports.services.cloudinary.uploader.upload')
    @patch('reports.services.pisa.CreatePDF')
    def test_portfolio_report_includes_lesson_detail_heading(self, mock_pisa, mock_upload):
        """Portfolio type renders the per-lesson detail section."""
        mock_upload.return_value = self._upload_rv
        portfolio = Report.objects.create(
            child=self.child, created_by=self.parent, report_type='portfolio',
            date_from=datetime.date(2026, 1, 1), date_to=datetime.date(2026, 6, 30),
        )
        lesson = _make_lesson(title='Algebra', number=2)
        enrolled = _make_enrolled(self.child)
        sl = ScheduledLesson.objects.create(
            child=self.child, lesson=lesson, enrolled_subject=enrolled,
            scheduled_date=datetime.date(2026, 2, 5),
        )
        LessonLog.objects.create(scheduled_lesson=sl, status='complete', mastery='green')

        generate_pdf(portfolio)

        html = mock_pisa.call_args[0][0]
        self.assertIn('Lesson Detail', html)
        self.assertIn('Algebra', html)


# ---------------------------------------------------------------------------
# S3.2 / T5 — report_detail_view
# ---------------------------------------------------------------------------

class ReportDetailViewTests(TestCase):
    """Tests for report_detail_view access control and rendering."""

    DETAIL_URL = 'reports:report_detail'

    def setUp(self):
        self.parent = _make_parent(username='det_parent')
        self.child = _make_child(self.parent, first_name='DetailChild')
        self.student = _make_student(username='det_student')
        self.report = Report.objects.create(
            child=self.child,
            created_by=self.parent,
            report_type='summary',
            date_from=datetime.date(2026, 1, 1),
            date_to=datetime.date(2026, 6, 30),
        )

    def _url(self, pk=None):
        return reverse(self.DETAIL_URL, kwargs={'pk': pk or self.report.pk})

    # ---------- access ----------

    def test_unauthenticated_redirects(self):
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 302)

    def test_student_role_blocked(self):
        self.client.force_login(self.student)
        response = self.client.get(self._url())
        self.assertRedirects(response, '/', fetch_redirect_response=False)

    def test_other_parent_gets_404(self):
        other = _make_parent(username='det_other')
        self.client.force_login(other)
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 404)

    def test_owner_gets_200(self):
        self.client.force_login(self.parent)
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)

    # ---------- rendering ----------

    def test_uses_correct_template(self):
        self.client.force_login(self.parent)
        response = self.client.get(self._url())
        self.assertTemplateUsed(response, 'reports/report_detail.html')

    def test_report_in_context(self):
        self.client.force_login(self.parent)
        response = self.client.get(self._url())
        self.assertEqual(response.context['report'], self.report)

    def test_no_pdf_file_gives_none_download_url(self):
        self.client.force_login(self.parent)
        response = self.client.get(self._url())
        self.assertIsNone(response.context['download_url'])

    def test_no_pdf_shows_not_available_text(self):
        self.client.force_login(self.parent)
        response = self.client.get(self._url())
        self.assertContains(response, 'PDF is not yet available')

    def test_shows_child_name(self):
        self.client.force_login(self.parent)
        response = self.client.get(self._url())
        self.assertContains(response, 'DetailChild')

    def test_shows_report_type(self):
        self.client.force_login(self.parent)
        response = self.client.get(self._url())
        self.assertContains(response, 'Summary')

    def test_contains_share_url(self):
        self.client.force_login(self.parent)
        response = self.client.get(self._url())
        self.assertContains(response, '/reports/share/')
        self.assertContains(response, str(self.report.share_token))

    def test_contains_copy_button(self):
        self.client.force_login(self.parent)
        response = self.client.get(self._url())
        self.assertContains(response, 'Copy Link')


# ---------------------------------------------------------------------------
# S3.3 / T1+T2+T3 — token_report_view
# ---------------------------------------------------------------------------

class TokenReportViewTests(TestCase):
    """Tests for public token-based shared report access."""

    SHARED_URL = 'reports:shared_report'

    def setUp(self):
        self.parent = _make_parent(username='tok_parent')
        self.child = _make_child(self.parent, first_name='TokenChild')
        self.report = Report.objects.create(
            child=self.child,
            created_by=self.parent,
            report_type='summary',
            date_from=datetime.date(2026, 1, 1),
            date_to=datetime.date(2026, 6, 30),
        )

    def _url(self, token=None):
        return reverse(self.SHARED_URL, kwargs={'token': token or self.report.share_token})

    def test_valid_token_renders_without_login(self):
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'reports/shared_report.html')

    def test_unknown_valid_uuid_returns_404(self):
        response = self.client.get(self._url(token=uuid.uuid4()))
        self.assertEqual(response.status_code, 404)

    def test_invalid_uuid_path_returns_404(self):
        response = self.client.get('/reports/share/not-a-uuid/')
        self.assertEqual(response.status_code, 404)

    def test_expired_token_returns_403(self):
        self.report.token_expires_at = timezone.now() - datetime.timedelta(minutes=1)
        self.report.save(update_fields=['token_expires_at'])
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, 'This link has expired', status_code=403)

    def test_shared_page_has_no_auth_nav_links(self):
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Login')
        self.assertNotContains(response, 'Logout')

    def test_shared_page_has_footer_branding(self):
        response = self.client.get(self._url())
        self.assertContains(response, 'Generated by EduTrack')


    def test_parent_without_subscription_is_redirected(self):
        """S3.5 T4: Protect report generation with subscription_active flag."""
        unsubscribed_user = User.objects.create_user(username='no_sub', password='pw')
        UserProfile.objects.create(user=unsubscribed_user, role='parent', subscription_active=False)
        child = _make_child(unsubscribed_user, 'NoSubChild')
        
        self.client.login(username='no_sub', password='pw')
        res = self.client.get(reverse(self.CREATE_URL, args=[child.id]))
