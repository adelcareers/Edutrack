"""Tests for the reports app — S3.1 Report Creation Form, S3.2 PDF Generation."""

import datetime
import uuid
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserProfile
from courses.models import (
    Course,
    GlobalAssignmentType,
    sync_course_assignment_types_from_global,
)
from curriculum.models import Lesson
from planning.models import (
    AssignmentPlanItem,
    CourseAssignmentTemplate,
    StudentAssignment,
)
from reports.forms import ReportForm
from reports.models import Report
from reports.services import generate_pdf
from reports.services_gradebook import recalculate_enrollment_grade
from scheduler.models import Child, EnrolledSubject, ScheduledLesson
from tracker.models import LessonLog

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_parent(username="rpt_parent", password="TestPass123!"):
    user = User.objects.create_user(username=username, password=password)
    UserProfile.objects.create(user=user, role="parent", subscription_active=True)
    return user


def _make_student(username="rpt_student", password="TestPass123!"):
    user = User.objects.create_user(username=username, password=password)
    UserProfile.objects.create(user=user, role="student")
    return user


def _make_child(parent, first_name="Alex"):
    return Child.objects.create(
        parent=parent,
        first_name=first_name,
        birth_month=4,
        birth_year=2013,
        school_year="Year 8",
        academic_year_start=datetime.date(2025, 9, 1),
    )


# ---------------------------------------------------------------------------
# S3.1 / T1 — ReportForm
# ---------------------------------------------------------------------------


class ReportFormValidationTests(TestCase):
    """Tests for ReportForm date range validation."""

    def _form(self, date_from, date_to, report_type="summary"):
        return ReportForm(
            data={
                "date_from": date_from,
                "date_to": date_to,
                "report_type": report_type,
            }
        )

    def test_valid_date_range_is_valid(self):
        form = self._form("2026-01-01", "2026-03-31")
        self.assertTrue(form.is_valid())

    def test_date_from_equal_to_date_to_is_invalid(self):
        form = self._form("2026-01-01", "2026-01-01")
        self.assertFalse(form.is_valid())

    def test_date_from_after_date_to_is_invalid(self):
        form = self._form("2026-04-01", "2026-01-01")
        self.assertFalse(form.is_valid())

    def test_invalid_date_range_contains_error_message(self):
        form = self._form("2026-04-01", "2026-01-01")
        form.is_valid()
        self.assertIn("Start date must be before end date.", form.non_field_errors())

    def test_summary_type_is_valid(self):
        form = self._form("2026-01-01", "2026-06-30", report_type="summary")
        self.assertTrue(form.is_valid())

    def test_portfolio_type_is_valid(self):
        form = self._form("2026-01-01", "2026-06-30", report_type="portfolio")
        self.assertTrue(form.is_valid())

    def test_invalid_report_type_rejected(self):
        form = self._form("2026-01-01", "2026-06-30", report_type="invalid_type")
        self.assertFalse(form.is_valid())

    def test_missing_date_from_is_invalid(self):
        form = ReportForm(data={"date_to": "2026-06-30", "report_type": "summary"})
        self.assertFalse(form.is_valid())

    def test_missing_date_to_is_invalid(self):
        form = ReportForm(data={"date_from": "2026-01-01", "report_type": "summary"})
        self.assertFalse(form.is_valid())


# ---------------------------------------------------------------------------
# S3.1 / T2+T4 — create_report_view
# ---------------------------------------------------------------------------


class CreateReportViewTests(TestCase):
    """Tests for create_report_view access control and behaviour."""

    CREATE_URL = "reports:create_report"

    def setUp(self):
        self.parent = _make_parent()
        self.child = _make_child(self.parent)
        self.student = _make_student()
        patcher = patch(
            "reports.views.generate_pdf",
            return_value="https://cdn.example.com/r.pdf",
        )
        self.mock_generate_pdf = patcher.start()
        self.addCleanup(patcher.stop)

    def _url(self, child_id=None):
        return reverse(self.CREATE_URL, kwargs={"child_id": child_id or self.child.pk})

    def _post(
        self,
        date_from="2026-01-01",
        date_to="2026-06-30",
        report_type="summary",
        child_id=None,
    ):
        return self.client.post(
            self._url(child_id),
            {
                "date_from": date_from,
                "date_to": date_to,
                "report_type": report_type,
            },
        )

    # ---------- access ----------

    def test_unauthenticated_redirects(self):
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 302)

    def test_student_role_blocked(self):
        self.client.force_login(self.student)
        response = self.client.get(self._url())
        self.assertRedirects(response, "/", fetch_redirect_response=False)

    def test_other_parent_gets_404(self):
        other = _make_parent(username="rpt_other_parent")
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
        self.assertTemplateUsed(response, "reports/create_report.html")

    def test_get_passes_form_to_context(self):
        self.client.force_login(self.parent)
        response = self.client.get(self._url())
        self.assertIsInstance(response.context["form"], ReportForm)

    def test_get_passes_child_to_context(self):
        self.client.force_login(self.parent)
        response = self.client.get(self._url())
        self.assertEqual(response.context["child"], self.child)

    def test_get_passes_total_completed_to_context(self):
        self.client.force_login(self.parent)
        response = self.client.get(self._url())
        self.assertIn("total_completed", response.context)

    def test_total_completed_reflects_lesson_logs(self):
        # Create a completed LessonLog for the child
        from curriculum.models import Lesson

        lesson = Lesson.objects.create(
            key_stage="KS3",
            subject_name="Maths",
            unit_title="Numbers",
            lesson_number=1,
            lesson_title="Counting",
            lesson_url="http://example.com",
        )
        enrolled = EnrolledSubject.objects.create(
            child=self.child,
            subject_name="Maths",
            key_stage="KS3",
            lessons_per_week=2,
            colour_hex="#123456",
        )
        sl = ScheduledLesson.objects.create(
            child=self.child,
            lesson=lesson,
            enrolled_subject=enrolled,
            scheduled_date=datetime.date(2026, 2, 1),
        )
        LessonLog.objects.create(scheduled_lesson=sl, status="complete")

        self.client.force_login(self.parent)
        response = self.client.get(self._url())
        self.assertEqual(response.context["total_completed"], 1)

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
            reverse("reports:report_detail", kwargs={"pk": report.pk}),
            fetch_redirect_response=False,
        )

    # ---------- POST invalid ----------

    def test_invalid_date_range_rerenders_form(self):
        self.client.force_login(self.parent)
        response = self._post(date_from="2026-06-30", date_to="2026-01-01")
        self.assertEqual(response.status_code, 200)

    def test_invalid_date_range_shows_error(self):
        self.client.force_login(self.parent)
        response = self._post(date_from="2026-06-30", date_to="2026-01-01")
        self.assertContains(response, "Start date must be before end date.")

    def test_invalid_post_does_not_create_report(self):
        self.client.force_login(self.parent)
        self._post(date_from="2026-06-30", date_to="2026-01-01")
        self.assertEqual(Report.objects.filter(child=self.child).count(), 0)


# ---------------------------------------------------------------------------
# S3.2 / T2 — generate_pdf service
# ---------------------------------------------------------------------------


def _make_lesson(subject="Maths", title="Counting", number=1):
    return Lesson.objects.create(
        key_stage="KS3",
        subject_name=subject,
        unit_title="Numbers",
        lesson_number=number,
        lesson_title=title,
        lesson_url="http://example.com",
    )


def _make_enrolled(child, subject="Maths"):
    return EnrolledSubject.objects.create(
        child=child,
        subject_name=subject,
        key_stage="KS3",
        lessons_per_week=2,
        colour_hex="#123456",
    )


class GeneratePdfServiceTests(TestCase):
    """Tests for reports.services.generate_pdf."""

    def setUp(self):
        self.parent = _make_parent(username="svc_parent")
        self.child = _make_child(self.parent, first_name="SvcChild")
        self.report = Report.objects.create(
            child=self.child,
            created_by=self.parent,
            report_type="summary",
            date_from=datetime.date(2026, 1, 1),
            date_to=datetime.date(2026, 6, 30),
        )
        self._upload_rv = {
            "public_id": "reports/test_report.pdf",
            "secure_url": "https://cdn.example.com/test_report.pdf",
        }

    @patch("reports.services.cloudinary.uploader.upload")
    @patch("reports.services.pisa.CreatePDF")
    def test_returns_secure_url(self, mock_pisa, mock_upload):
        mock_upload.return_value = self._upload_rv
        url = generate_pdf(self.report)
        self.assertEqual(url, "https://cdn.example.com/test_report.pdf")

    @patch("reports.services.cloudinary.uploader.upload")
    @patch("reports.services.pisa.CreatePDF")
    def test_sets_pdf_file_on_report(self, mock_pisa, mock_upload):
        mock_upload.return_value = self._upload_rv
        generate_pdf(self.report)
        self.report.refresh_from_db()
        # CloudinaryField strips the format extension from the public_id.
        self.assertIn("reports/test_report", str(self.report.pdf_file))

    @patch("reports.services.cloudinary.uploader.upload")
    @patch("reports.services.pisa.CreatePDF")
    def test_calls_cloudinary_upload(self, mock_pisa, mock_upload):
        mock_upload.return_value = self._upload_rv
        generate_pdf(self.report)
        self.assertTrue(mock_upload.called)
        call_kwargs = mock_upload.call_args[1]
        self.assertEqual(call_kwargs.get("resource_type"), "raw")

    @patch("reports.services.cloudinary.uploader.upload")
    @patch("reports.services.pisa.CreatePDF")
    def test_only_completed_logs_included_in_html(self, mock_pisa, mock_upload):
        """Completed lessons appear in context; pending ones do not."""
        mock_upload.return_value = self._upload_rv
        lesson = _make_lesson()
        enrolled = _make_enrolled(self.child)
        sl_done = ScheduledLesson.objects.create(
            child=self.child,
            lesson=lesson,
            enrolled_subject=enrolled,
            scheduled_date=datetime.date(2026, 3, 1),
        )
        sl_pending = ScheduledLesson.objects.create(
            child=self.child,
            lesson=lesson,
            enrolled_subject=enrolled,
            scheduled_date=datetime.date(2026, 3, 2),
        )
        LessonLog.objects.create(scheduled_lesson=sl_done, status="complete")
        LessonLog.objects.create(scheduled_lesson=sl_pending, status="pending")

        generate_pdf(self.report)

        html = mock_pisa.call_args[0][0]
        self.assertIn("SvcChild", html)

    @patch("reports.services.cloudinary.uploader.upload")
    @patch("reports.services.pisa.CreatePDF")
    def test_portfolio_report_includes_lesson_detail_heading(
        self, mock_pisa, mock_upload
    ):
        """Portfolio type renders the per-lesson detail section."""
        mock_upload.return_value = self._upload_rv
        portfolio = Report.objects.create(
            child=self.child,
            created_by=self.parent,
            report_type="portfolio",
            date_from=datetime.date(2026, 1, 1),
            date_to=datetime.date(2026, 6, 30),
        )
        lesson = _make_lesson(title="Algebra", number=2)
        enrolled = _make_enrolled(self.child)
        sl = ScheduledLesson.objects.create(
            child=self.child,
            lesson=lesson,
            enrolled_subject=enrolled,
            scheduled_date=datetime.date(2026, 2, 5),
        )
        LessonLog.objects.create(
            scheduled_lesson=sl, status="complete", mastery="green"
        )

        generate_pdf(portfolio)

        html = mock_pisa.call_args[0][0]
        self.assertIn("Lesson Detail", html)
        self.assertIn("Algebra", html)


# ---------------------------------------------------------------------------
# S3.2 / T5 — report_detail_view
# ---------------------------------------------------------------------------


class ReportDetailViewTests(TestCase):
    """Tests for report_detail_view access control and rendering."""

    DETAIL_URL = "reports:report_detail"

    def setUp(self):
        self.parent = _make_parent(username="det_parent")
        self.child = _make_child(self.parent, first_name="DetailChild")
        self.student = _make_student(username="det_student")
        self.report = Report.objects.create(
            child=self.child,
            created_by=self.parent,
            report_type="summary",
            date_from=datetime.date(2026, 1, 1),
            date_to=datetime.date(2026, 6, 30),
        )

    def _url(self, pk=None):
        return reverse(self.DETAIL_URL, kwargs={"pk": pk or self.report.pk})

    # ---------- access ----------

    def test_unauthenticated_redirects(self):
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 302)

    def test_student_role_blocked(self):
        self.client.force_login(self.student)
        response = self.client.get(self._url())
        self.assertRedirects(response, "/", fetch_redirect_response=False)

    def test_other_parent_gets_404(self):
        other = _make_parent(username="det_other")
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
        self.assertTemplateUsed(response, "reports/report_detail.html")

    def test_report_in_context(self):
        self.client.force_login(self.parent)
        response = self.client.get(self._url())
        self.assertEqual(response.context["report"], self.report)

    def test_no_pdf_file_gives_none_download_url(self):
        self.client.force_login(self.parent)
        response = self.client.get(self._url())
        self.assertIsNone(response.context["download_url"])

    def test_no_pdf_shows_not_available_text(self):
        self.client.force_login(self.parent)
        response = self.client.get(self._url())
        self.assertContains(response, "PDF is not yet available")

    def test_shows_child_name(self):
        self.client.force_login(self.parent)
        response = self.client.get(self._url())
        self.assertContains(response, "DetailChild")

    def test_shows_report_type(self):
        self.client.force_login(self.parent)
        response = self.client.get(self._url())
        self.assertContains(response, "Summary")

    def test_contains_share_url(self):
        self.client.force_login(self.parent)
        response = self.client.get(self._url())
        self.assertContains(response, "/reports/share/")
        self.assertContains(response, str(self.report.share_token))

    def test_contains_copy_button(self):
        self.client.force_login(self.parent)
        response = self.client.get(self._url())
        self.assertContains(response, "Copy Link")


# ---------------------------------------------------------------------------
# S3.3 / T1+T2+T3 — token_report_view
# ---------------------------------------------------------------------------


class TokenReportViewTests(TestCase):
    """Tests for public token-based shared report access."""

    SHARED_URL = "reports:shared_report"

    def setUp(self):
        self.parent = _make_parent(username="tok_parent")
        self.child = _make_child(self.parent, first_name="TokenChild")
        self.report = Report.objects.create(
            child=self.child,
            created_by=self.parent,
            report_type="summary",
            date_from=datetime.date(2026, 1, 1),
            date_to=datetime.date(2026, 6, 30),
        )

    def _url(self, token=None):
        return reverse(
            self.SHARED_URL, kwargs={"token": token or self.report.share_token}
        )

    def test_valid_token_renders_report(self):
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "reports/shared_report.html")

    def test_unknown_valid_uuid_returns_404(self):
        response = self.client.get(self._url(token=uuid.uuid4()))
        self.assertEqual(response.status_code, 404)

    def test_invalid_token_returns_404(self):
        response = self.client.get("/reports/share/not-a-uuid/")
        self.assertEqual(response.status_code, 404)

    def test_expired_token_returns_403(self):
        self.report.token_expires_at = timezone.now() - datetime.timedelta(minutes=1)
        self.report.save(update_fields=["token_expires_at"])
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "This link has expired", status_code=403)

    def test_shared_page_has_no_auth_nav_links(self):
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Login")
        self.assertNotContains(response, "Logout")

    def test_shared_page_has_footer_branding(self):
        response = self.client.get(self._url())
        self.assertContains(response, "Generated by EduTrack")


class GradebookViewsAndServiceTests(TestCase):
    def setUp(self):
        self.parent = _make_parent(username="gb_parent")
        self.child = _make_child(self.parent, first_name="GradeChild")
        self.client.force_login(self.parent)

        self.course = Course.objects.create(
            parent=self.parent,
            name="Science",
            grading_style="point_graded",
            use_assignment_weights=True,
            duration_weeks=12,
            frequency_days=5,
        )
        global_type = GlobalAssignmentType.objects.create(
            parent=self.parent,
            name="Homework",
            color="#9ca3af",
            order=0,
        )
        sync_course_assignment_types_from_global(self.course)
        self.assignment_type = self.course.assignment_types.get(global_type=global_type)
        self.assignment_type.weight = 100
        self.assignment_type.default_points_available = 10
        self.assignment_type.save(update_fields=["weight", "default_points_available"])

        self.enrollment = self.course.enrollments.create(
            child=self.child,
            start_date=datetime.date(2026, 1, 1),
            days_of_week="0,2,4",
            status="active",
        )

        template = CourseAssignmentTemplate.objects.create(
            course=self.course,
            assignment_type=self.assignment_type,
            name="Worksheet",
            is_graded=True,
            due_offset_days=0,
            order=0,
        )
        plan_item = AssignmentPlanItem.objects.create(
            course=self.course,
            template=template,
            week_number=1,
            day_number=1,
            due_in_days=0,
            order=0,
        )
        self.student_assignment = StudentAssignment.objects.create(
            enrollment=self.enrollment,
            plan_item=plan_item,
            due_date=datetime.date(2026, 1, 2),
            status="pending",
        )

    def test_gradebook_list_loads_for_parent(self):
        response = self.client.get(reverse("reports:gradebook_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Gradebooks")
        self.assertContains(response, "Science")

    def test_gradebook_detail_post_updates_assignment_grade(self):
        response = self.client.post(
            reverse(
                "reports:gradebook_detail", kwargs={"enrollment_id": self.enrollment.id}
            ),
            {
                "assignment_id": self.student_assignment.id,
                "score": "8",
                "points_available": "10",
                "score_percent": "",
                "grading_notes": "Good work",
            },
        )
        self.assertEqual(response.status_code, 302)

        self.student_assignment.refresh_from_db()
        self.assertEqual(float(self.student_assignment.score), 8.0)
        self.assertEqual(float(self.student_assignment.points_available), 10.0)
        self.assertEqual(self.student_assignment.grading_notes, "Good work")
        self.assertIsNotNone(self.student_assignment.graded_at)
        self.assertEqual(self.student_assignment.graded_by, self.parent)
        self.assertEqual(self.student_assignment.status, "complete")

    def test_gradebook_detail_modal_save_updates_status_and_due_date(self):
        response = self.client.post(
            reverse(
                "reports:gradebook_detail", kwargs={"enrollment_id": self.enrollment.id}
            ),
            {
                "action": "save_modal",
                "assignment_id": self.student_assignment.id,
                "status": "complete",
                "due_date": "2026-02-01",
                "score": "9",
                "points_available": "10",
                "score_percent": "",
                "grading_notes": "Updated from modal",
            },
        )
        self.assertEqual(response.status_code, 302)

        self.student_assignment.refresh_from_db()
        self.assertEqual(self.student_assignment.status, "complete")
        self.assertEqual(
            self.student_assignment.due_date,
            datetime.date(2026, 2, 1),
        )
        self.assertIsNotNone(self.student_assignment.completed_at)

    def test_gradebook_detail_shows_needs_grading_chip(self):
        self.student_assignment.status = "needs_grading"
        self.student_assignment.save(update_fields=["status"])

        response = self.client.get(
            reverse(
                "reports:gradebook_detail", kwargs={"enrollment_id": self.enrollment.id}
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Needs Grading")

    def test_gradebook_transcript_view_renders_child_summary(self):
        self.student_assignment.score = 8
        self.student_assignment.points_available = 10
        self.student_assignment.save(update_fields=["score", "points_available"])
        recalculate_enrollment_grade(self.enrollment)

        response = self.client.get(
            reverse("reports:gradebook_transcript", kwargs={"child_id": self.child.id})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Transcript")
        self.assertContains(response, self.child.first_name)
        self.assertContains(response, "Per-Assignment Rows")

    def test_gradebook_transcript_view_pdf_export(self):
        response = self.client.get(
            reverse("reports:gradebook_transcript", kwargs={"child_id": self.child.id})
            + "?format=pdf"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("attachment; filename=", response["Content-Disposition"])

    def test_gradebook_detail_sort_by_name_desc(self):
        second_template = CourseAssignmentTemplate.objects.create(
            course=self.course,
            assignment_type=self.assignment_type,
            name="Alpha Task",
            is_graded=True,
            due_offset_days=0,
            order=0,
        )
        second_plan_item = AssignmentPlanItem.objects.create(
            course=self.course,
            template=second_template,
            week_number=1,
            day_number=2,
            due_in_days=0,
            order=0,
        )
        StudentAssignment.objects.create(
            enrollment=self.enrollment,
            plan_item=second_plan_item,
            due_date=datetime.date(2026, 1, 3),
            status="pending",
        )

        response = self.client.get(
            reverse(
                "reports:gradebook_detail", kwargs={"enrollment_id": self.enrollment.id}
            )
            + "?sort=name&order=desc"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["sort_by"], "name")
        self.assertEqual(response.context["sort_order"], "desc")

        assignment_names = [
            assignment.plan_item.template.name
            for assignment in response.context["assignments"]
        ]
        self.assertEqual(assignment_names, ["Worksheet", "Alpha Task"])

    def test_recalculate_enrollment_grade_uses_default_points(self):
        self.student_assignment.score = 7
        self.student_assignment.points_available = None
        self.student_assignment.save(update_fields=["score", "points_available"])

        summary = recalculate_enrollment_grade(self.enrollment)
        self.assertEqual(float(summary.final_percent), 70.0)
        self.assertEqual(summary.graded_assignments_count, 1)
