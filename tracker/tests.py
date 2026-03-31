"""Tests for the tracker app — S2.1 Weekly Calendar View."""

import datetime
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from accounts.models import ParentSettings, UserProfile
from courses.models import AssignmentType, Course
from curriculum.models import Lesson
from planning.models import (
    ActivityProgress,
    AssignmentComment,
    AssignmentPlanItem,
    AssignmentSubmission,
    CourseAssignmentTemplate,
    PlanItem,
    StudentAssignment,
)
from scheduler.models import Child, EnrolledSubject, ScheduledLesson
from tracker.models import EvidenceFile, LessonComment, LessonLog

# Minimal fake Cloudinary upload response used by EvidenceUploadTests.
_FAKE_CLOUDINARY = {
    "public_id": "edutrack_test/fake_evidence",
    "version": 1234567890,
    "secure_url": "https://res.cloudinary.com/test/raw/upload/v1234567890/fake_evidence",
    "url": "http://res.cloudinary.com/test/raw/upload/v1234567890/fake_evidence",
    "resource_type": "raw",
    "type": "upload",
    "format": "png",
    "bytes": 100,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_parent(username="cal_parent", password="TestPass123!"):
    user = User.objects.create_user(username=username, password=password)
    UserProfile.objects.create(user=user, role="parent")
    return user


def _make_student(username="cal_student", password="TestPass123!"):
    user = User.objects.create_user(username=username, password=password)
    UserProfile.objects.create(user=user, role="student")
    return user


def _make_child(parent, student_user=None, first_name="Sam", is_setup_complete=True):
    return Child.objects.create(
        parent=parent,
        first_name=first_name,
        birth_month=3,
        birth_year=2014,
        school_year="Year 7",
        academic_year_start=datetime.date(2025, 9, 1),
        student_user=student_user,
        is_setup_complete=is_setup_complete,
    )


def _make_lesson(subject="Maths", title="Counting", key_stage="KS3"):
    import uuid

    return Lesson.objects.create(
        key_stage=key_stage,
        subject_name=subject,
        programme_slug="maths-ks3",
        year="Year 7",
        unit_slug="number",
        unit_title="Number",
        lesson_number=1,
        lesson_title=title,
        lesson_url=f"https://example.com/lesson/{uuid.uuid4()}",
    )


def _make_enrolled_subject(child, subject_name="Maths"):
    return EnrolledSubject.objects.create(
        child=child,
        subject_name=subject_name,
        key_stage="KS3",
        lessons_per_week=2,
        colour_hex="#3B82F6",
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

    CALENDAR_URL = "tracker:calendar"
    CALENDAR_WEEK_URL = "tracker:calendar_week"

    def setUp(self):
        self.parent = _make_parent()
        self.student = _make_student()
        self.child = _make_child(self.parent, student_user=self.student)
        self.url = reverse(self.CALENDAR_URL)

    # ---------- access ----------

    def test_unauthenticated_redirects_to_login(self):
        response = self.client.get(self.url)
        self.assertRedirects(response, f"/accounts/login/?next={self.url}")

    def test_parent_role_blocked(self):
        self.client.force_login(self.parent)
        response = self.client.get(self.url)
        self.assertRedirects(response, "/", fetch_redirect_response=False)

    # ---------- GET returns 200 ----------

    def test_student_gets_200(self):
        self.client.force_login(self.student)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_uses_calendar_template(self):
        self.client.force_login(self.student)
        response = self.client.get(self.url)
        self.assertTemplateUsed(response, "tracker/calendar.html")

    # ---------- context ----------

    def test_context_has_required_keys(self):
        self.client.force_login(self.student)
        response = self.client.get(self.url)
        for key in ("days", "year", "week", "today"):
            self.assertIn(key, response.context)

    def test_days_has_seven_columns(self):
        self.client.force_login(self.student)
        response = self.client.get(self.url)
        days = response.context["days"]
        self.assertEqual(len(days), 7)
        for name in (
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ):
            self.assertIn(name, days)

    def test_default_week_matches_today(self):
        self.client.force_login(self.student)
        response = self.client.get(self.url)
        today = datetime.date.today()
        iso_year, iso_week, _ = today.isocalendar()
        self.assertEqual(response.context["year"], iso_year)
        self.assertEqual(response.context["week"], iso_week)

    # ---------- specific week URL ----------

    def test_specific_week_url_sets_context(self):
        self.client.force_login(self.student)
        url = reverse(self.CALENDAR_WEEK_URL, kwargs={"year": 2025, "week": 1})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["year"], 2025)
        self.assertEqual(response.context["week"], 1)

    # ---------- lessons in correct day ----------

    def test_lesson_appears_in_correct_day(self):
        # ISO week 1, 2025 starts Monday 30 Dec 2024
        monday = datetime.date.fromisocalendar(2025, 1, 1)  # Monday
        lesson = _make_lesson()
        enrolled = _make_enrolled_subject(self.child)
        _make_scheduled_lesson(self.child, lesson, enrolled, monday)

        self.client.force_login(self.student)
        url = reverse(self.CALENDAR_WEEK_URL, kwargs={"year": 2025, "week": 1})
        response = self.client.get(url)
        monday_lessons = response.context["days"]["monday"]["lessons"]
        self.assertEqual(len(monday_lessons), 1)
        self.assertEqual(monday_lessons[0].lesson.lesson_title, "Counting")

    def test_lesson_on_wednesday_not_in_monday(self):
        wednesday = datetime.date.fromisocalendar(2025, 1, 3)
        lesson = _make_lesson()
        enrolled = _make_enrolled_subject(self.child)
        _make_scheduled_lesson(self.child, lesson, enrolled, wednesday)

        self.client.force_login(self.student)
        url = reverse(self.CALENDAR_WEEK_URL, kwargs={"year": 2025, "week": 1})
        response = self.client.get(url)
        self.assertEqual(len(response.context["days"]["monday"]["lessons"]), 0)
        self.assertEqual(len(response.context["days"]["wednesday"]["lessons"]), 1)

    # ---------- empty day ----------

    def test_empty_day_has_no_lessons(self):
        self.client.force_login(self.student)
        response = self.client.get(self.url)
        for name, day in response.context["days"].items():
            self.assertEqual(day["lessons"], [])

    def test_empty_day_renders_no_lessons_message(self):
        self.client.force_login(self.student)
        response = self.client.get(self.url)
        self.assertContains(response, "No lessons")

    # ---------- student without child_profile ----------

    def test_student_without_child_profile_gets_200(self):
        orphan = User.objects.create_user(username="orphan_stu", password="Pass123!")
        UserProfile.objects.create(user=orphan, role="student")
        self.client.force_login(orphan)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        for name, day in response.context["days"].items():
            self.assertEqual(day["lessons"], [])


class CalendarNavigationTests(TestCase):
    """Tests for S2.2 week navigation — prev/next/today links and week_display."""

    CALENDAR_URL = "tracker:calendar"
    CALENDAR_WEEK_URL = "tracker:calendar_week"

    def setUp(self):
        self.student = _make_student(username="nav_student")
        self.client.force_login(self.student)

    def _get_week(self, year, week):
        url = reverse(self.CALENDAR_WEEK_URL, kwargs={"year": year, "week": week})
        return self.client.get(url)

    # ---------- context keys present ----------

    def test_nav_context_keys_present(self):
        response = self.client.get(reverse(self.CALENDAR_URL))
        for key in (
            "prev_year",
            "prev_week",
            "next_year",
            "next_week",
            "today_year",
            "today_week",
            "week_display",
        ):
            self.assertIn(key, response.context, msg=f"Missing context key: {key}")

    # ---------- prev week ----------

    def test_prev_week_is_one_week_earlier(self):
        # Week 10 2026: Monday = 2 Mar 2026 → prev = week 9 2026
        response = self._get_week(2026, 10)
        self.assertEqual(response.context["prev_year"], 2026)
        self.assertEqual(response.context["prev_week"], 9)

    def test_prev_week_crosses_year_boundary(self):
        # ISO week 1 2026: Monday = 29 Dec 2025 → prev week = week 52/53 2025
        response = self._get_week(2026, 1)
        # prev_monday = 22 Dec 2025 → ISO week 52, year 2025
        self.assertEqual(response.context["prev_year"], 2025)
        self.assertEqual(response.context["prev_week"], 52)

    # ---------- next week ----------

    def test_next_week_is_one_week_later(self):
        response = self._get_week(2026, 10)
        self.assertEqual(response.context["next_year"], 2026)
        self.assertEqual(response.context["next_week"], 11)

    def test_next_week_crosses_year_boundary(self):
        # Last ISO week of 2026 — year 2026 has 52 ISO weeks; week 52 Mon = 21 Dec 2026
        response = self._get_week(2026, 52)
        # next_monday = 28 Dec 2026 → ISO week 53? No; 28 Dec 2026 is week 53 of 2026? Let's check:
        # 28 Dec 2026 isocalendar → year 2026, week 53 (2026 has 53 ISO weeks? No — need to verify)
        # Actually: 28 Dec 2026 is a Monday; ISO week 53 of 2026 exists if 1 Jan 2027 is in week 53.
        # 1 Jan 2027 = Friday → belongs to week 53 of 2026. So next = (2026, 53).
        # Then week 53 2026 next = week 1 2027.
        next_y = response.context["next_year"]
        next_w = response.context["next_week"]
        # Just verify it's a valid forward step
        curr_monday = datetime.date.fromisocalendar(2026, 52, 1)
        next_monday = datetime.date.fromisocalendar(next_y, next_w, 1)
        self.assertEqual((next_monday - curr_monday).days, 7)

    # ---------- today context ----------

    def test_today_context_matches_current_isoweek(self):
        response = self.client.get(reverse(self.CALENDAR_URL))
        today = datetime.date.today()
        iso_year, iso_week, _ = today.isocalendar()
        self.assertEqual(response.context["today_year"], iso_year)
        self.assertEqual(response.context["today_week"], iso_week)

    # ---------- week_display string ----------

    def test_week_display_same_month(self):
        # Week 10 2026: Mon 2 Mar – Sat 7 Mar 2026 → "Mar 02, 2026 — Mar 07, 2026"
        response = self._get_week(2026, 10)
        self.assertEqual(
            response.context["week_display"], "Mar 02, 2026 — Mar 07, 2026"
        )

    def test_week_display_cross_month(self):
        # Week 14 2026: Mon 30 Mar – Sat 4 Apr 2026 → "Mar 30, 2026 — Apr 04, 2026"
        response = self._get_week(2026, 14)
        self.assertEqual(
            response.context["week_display"], "Mar 30, 2026 — Apr 04, 2026"
        )

    # ---------- nav links rendered in template ----------

    def test_prev_link_in_rendered_output(self):
        response = self._get_week(2026, 10)
        prev_url = reverse(self.CALENDAR_WEEK_URL, kwargs={"year": 2026, "week": 9})
        self.assertContains(response, prev_url)

    def test_next_link_in_rendered_output(self):
        response = self._get_week(2026, 10)
        next_url = reverse(self.CALENDAR_WEEK_URL, kwargs={"year": 2026, "week": 11})
        self.assertContains(response, next_url)

    def test_today_button_in_rendered_output(self):
        response = self.client.get(reverse(self.CALENDAR_URL))
        today = datetime.date.today()
        iso_year, iso_week, _ = today.isocalendar()
        today_url = reverse(
            self.CALENDAR_WEEK_URL, kwargs={"year": iso_year, "week": iso_week}
        )
        self.assertContains(response, today_url)
        self.assertContains(response, "Today")


class IncompleteStudentAccessGuardTests(TestCase):
    def setUp(self):
        self.parent = _make_parent(username="draft_parent")
        self.student = _make_student(username="draft_student")
        _make_child(
            self.parent,
            student_user=self.student,
            first_name="Draft",
            is_setup_complete=False,
        )
        self.client.force_login(self.student)

    def test_student_home_is_blocked_until_setup_is_complete(self):
        response = self.client.get(reverse("tracker:home_assignments"))
        self.assertEqual(response.status_code, 403)

    def test_student_calendar_is_blocked_until_setup_is_complete(self):
        response = self.client.get(reverse("tracker:calendar"))
        self.assertEqual(response.status_code, 403)


class SubjectColourCardTests(TestCase):
    """Tests for S2.3 subject colour cards on the calendar."""

    CALENDAR_WEEK_URL = "tracker:calendar_week"

    def setUp(self):
        parent = _make_parent(username="colour_parent")
        self.student = _make_student(username="colour_student")
        self.child = _make_child(parent, student_user=self.student)
        self.lesson = _make_lesson()
        self.enrolled = _make_enrolled_subject(self.child)
        # Place lesson on the Monday of ISO week 10, 2026 (2 Mar 2026)
        self.monday = datetime.date.fromisocalendar(2026, 10, 1)
        self.sl = _make_scheduled_lesson(
            self.child, self.lesson, self.enrolled, self.monday
        )
        self.client.force_login(self.student)

    def _get(self):
        return self.client.get(
            reverse(self.CALENDAR_WEEK_URL, kwargs={"year": 2026, "week": 10})
        )

    # ---------- colour variable rendered ----------

    def test_subject_colour_hex_in_style_attribute(self):
        response = self._get()
        self.assertContains(response, f"--subject-colour: {self.enrolled.colour_hex}")

    def test_card_header_contains_subject_name(self):
        response = self._get()
        self.assertContains(response, self.enrolled.subject_name)

    def test_card_body_contains_lesson_title(self):
        response = self._get()
        self.assertContains(response, self.lesson.lesson_title)

    # ---------- no log — no badges, no dots ----------

    def test_no_badge_when_no_log(self):
        response = self._get()
        # No status-badge rendered when lesson has no log
        self.assertNotContains(response, "status-badge")
        self.assertNotContains(response, 'class="mastery-dot')

    # ---------- status badges ----------

    def test_complete_badge_rendered(self):
        LessonLog.objects.create(
            scheduled_lesson=self.sl,
            status="complete",
            mastery="unset",
            updated_by=self.student,
        )
        response = self._get()
        self.assertContains(response, "Complete")

    def test_skipped_badge_rendered(self):
        LessonLog.objects.create(
            scheduled_lesson=self.sl,
            status="skipped",
            mastery="unset",
            updated_by=self.student,
        )
        response = self._get()
        self.assertContains(response, "Skipped")

    # ---------- mastery dots ----------

    def test_green_mastery_dot_rendered(self):
        LessonLog.objects.create(
            scheduled_lesson=self.sl,
            status="complete",
            mastery="green",
            updated_by=self.student,
        )
        response = self._get()
        self.assertContains(response, "mastery-dot green")

    def test_amber_mastery_dot_rendered(self):
        LessonLog.objects.create(
            scheduled_lesson=self.sl,
            status="complete",
            mastery="amber",
            updated_by=self.student,
        )
        response = self._get()
        self.assertContains(response, "mastery-dot amber")

    def test_red_mastery_dot_rendered(self):
        LessonLog.objects.create(
            scheduled_lesson=self.sl,
            status="complete",
            mastery="red",
            updated_by=self.student,
        )
        response = self._get()
        self.assertContains(response, "mastery-dot red")

    def test_unset_mastery_shows_no_dot(self):
        LessonLog.objects.create(
            scheduled_lesson=self.sl,
            status="complete",
            mastery="unset",
            updated_by=self.student,
        )
        response = self._get()
        self.assertNotContains(response, 'class="mastery-dot')

    # ---------- different subjects get different colours ----------

    def test_two_subjects_have_different_colours(self):
        lesson2 = _make_lesson(subject="English", title="Grammar", key_stage="KS3")
        enrolled2 = EnrolledSubject.objects.create(
            child=self.child,
            subject_name="English",
            key_stage="KS3",
            lessons_per_week=2,
            colour_hex="#EF4444",
        )
        wednesday = self.monday + datetime.timedelta(days=2)
        _make_scheduled_lesson(self.child, lesson2, enrolled2, wednesday)
        response = self._get()
        self.assertContains(response, "--subject-colour: #3B82F6")
        self.assertContains(response, "--subject-colour: #EF4444")


class LessonDetailViewTests(TestCase):
    """Tests for S2.4 lesson_detail_view JSON endpoint."""

    DETAIL_URL = "tracker:lesson_detail"

    def setUp(self):
        self.parent = _make_parent(username="det_parent")
        self.student = _make_student(username="det_student")
        self.child = _make_child(self.parent, student_user=self.student)
        self.lesson = _make_lesson()
        self.enrolled = _make_enrolled_subject(self.child)
        self.monday = datetime.date.fromisocalendar(2026, 10, 1)
        self.sl = _make_scheduled_lesson(
            self.child, self.lesson, self.enrolled, self.monday
        )

    def _url(self, pk=None):
        return reverse(self.DETAIL_URL, kwargs={"scheduled_id": pk or self.sl.pk})

    # ---------- access ----------

    def test_unauthenticated_redirects(self):
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 302)

    def test_parent_can_fetch_child_lesson_detail(self):
        self.client.force_login(self.parent)
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], self.sl.pk)

    def test_student_returns_200_json(self):
        self.client.force_login(self.student)
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")

    # ---------- ownership ----------

    def test_other_student_gets_403(self):
        other_student = User.objects.create_user(username="other_stu", password="Pass!")
        UserProfile.objects.create(user=other_student, role="student")
        other_parent = _make_parent(username="other_par")
        other_child = _make_child(
            other_parent, student_user=other_student, first_name="Other"
        )
        self.client.force_login(other_student)
        response = self.client.get(
            self._url()
        )  # sl belongs to self.child, not other_child
        self.assertEqual(response.status_code, 403)

    def test_other_parent_gets_403(self):
        other_parent = _make_parent(username="det_other_parent")
        self.client.force_login(other_parent)
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 403)

    def test_student_without_child_profile_gets_403(self):
        orphan = User.objects.create_user(username="orphan2", password="Pass!")
        UserProfile.objects.create(user=orphan, role="student")
        self.client.force_login(orphan)
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 403)

    # ---------- JSON payload ----------

    def test_json_contains_required_keys(self):
        self.client.force_login(self.student)
        data = self.client.get(self._url()).json()
        for key in (
            "id",
            "lesson_title",
            "unit_title",
            "subject_name",
            "scheduled_date",
            "lesson_url",
            "colour_hex",
            "status",
            "status_label",
            "status_icon",
            "status_tone",
            "mastery",
            "student_notes",
            "scheduled_date_iso",
            "student_name",
            "completion_receipt_url",
            "completion_receipt_meta",
            "evidence_count",
            "submissions_count",
            "comments",
            "comments_count",
        ):
            self.assertIn(key, data, msg=f"Missing key: {key}")

    def test_json_lesson_title_correct(self):
        self.client.force_login(self.student)
        data = self.client.get(self._url()).json()
        self.assertEqual(data["lesson_title"], self.lesson.lesson_title)

    def test_json_subject_name_correct(self):
        self.client.force_login(self.student)
        data = self.client.get(self._url()).json()
        self.assertEqual(data["subject_name"], self.enrolled.subject_name)

    def test_json_colour_hex_correct(self):
        self.client.force_login(self.student)
        data = self.client.get(self._url()).json()
        self.assertEqual(data["colour_hex"], self.enrolled.colour_hex)

    def test_json_status_is_derived_when_no_log(self):
        self.client.force_login(self.student)
        data = self.client.get(self._url()).json()
        expected = (
            "overdue"
            if self.sl.scheduled_date < datetime.date.today()
            else "incomplete"
        )
        self.assertEqual(data["status"], expected)
        self.assertEqual(data["mastery"], "unset")

    def test_json_status_reflects_log(self):
        LessonLog.objects.create(
            scheduled_lesson=self.sl,
            status="complete",
            mastery="green",
            updated_by=self.student,
        )
        self.client.force_login(self.student)
        data = self.client.get(self._url()).json()
        self.assertEqual(data["status"], "complete")
        self.assertEqual(data["mastery"], "green")

    # ---------- template renders card with data-id ----------

    def test_calendar_card_has_data_id(self):
        self.client.force_login(self.student)
        url = reverse("tracker:calendar_week", kwargs={"year": 2026, "week": 10})
        response = self.client.get(url)
        self.assertContains(response, f'data-id="{self.sl.pk}"')


# ---------------------------------------------------------------------------
# S2.5 — Mark Lesson Complete or Skip
# ---------------------------------------------------------------------------


class LessonStatusUpdateTests(TestCase):
    """Tests for S2.5 update_lesson_status_view POST endpoint."""

    UPDATE_URL = "tracker:lesson_update"

    def setUp(self):
        self.parent = _make_parent(username="upd_parent")
        self.student = _make_student(username="upd_student")
        self.child = _make_child(self.parent, student_user=self.student)
        self.lesson = _make_lesson(title="Update Test Lesson")
        self.enrolled = _make_enrolled_subject(self.child, subject_name="Science")
        self.monday = datetime.date.fromisocalendar(2026, 12, 1)
        self.sl = _make_scheduled_lesson(
            self.child, self.lesson, self.enrolled, self.monday
        )

    def _url(self, pk=None):
        return reverse(self.UPDATE_URL, kwargs={"scheduled_id": pk or self.sl.pk})

    def _post(self, status, pk=None):
        return self.client.post(
            self._url(pk), {"status": status}, HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )

    # ---------- access ----------

    def test_unauthenticated_redirects(self):
        response = self._post("complete")
        self.assertEqual(response.status_code, 302)

    def test_parent_can_update_status(self):
        self.client.force_login(self.parent)
        response = self._post("complete")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "complete")

    def test_get_method_not_allowed(self):
        self.client.force_login(self.student)
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 405)

    # ---------- ownership ----------

    def test_other_student_gets_403(self):
        other_student = User.objects.create_user(
            username="upd_other_stu", password="Pass!"
        )
        UserProfile.objects.create(user=other_student, role="student")
        other_parent = _make_parent(username="upd_other_par")
        _make_child(other_parent, student_user=other_student, first_name="Other2")
        self.client.force_login(other_student)
        response = self._post("complete")
        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertEqual(data["error"], "forbidden")

    def test_student_without_child_profile_gets_403(self):
        orphan = User.objects.create_user(username="upd_orphan", password="Pass!")
        UserProfile.objects.create(user=orphan, role="student")
        self.client.force_login(orphan)
        response = self._post("complete")
        self.assertEqual(response.status_code, 403)

    # ---------- invalid status ----------

    def test_invalid_status_returns_400(self):
        self.client.force_login(self.student)
        response = self._post("in_progress")
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["error"], "invalid status")

    def test_empty_status_returns_400(self):
        self.client.force_login(self.student)
        response = self._post("")
        self.assertEqual(response.status_code, 400)

    # ---------- mark complete ----------

    def test_mark_complete_returns_success_json(self):
        self.client.force_login(self.student)
        response = self._post("complete")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["status"], "complete")

    def test_lesson_log_created_on_complete(self):
        self.client.force_login(self.student)
        self._post("complete")
        log = LessonLog.objects.get(scheduled_lesson=self.sl)
        self.assertEqual(log.status, "complete")

    def test_mark_complete_sets_completed_at(self):
        self.client.force_login(self.student)
        self._post("complete")
        log = LessonLog.objects.get(scheduled_lesson=self.sl)
        self.assertIsNotNone(log.completed_at)

    def test_hard_mode_blocks_student_complete_without_valid_receipt(self):
        settings, _ = ParentSettings.objects.get_or_create(user=self.parent)
        settings.receipt_enforcement_mode = "hard"
        settings.save(update_fields=["receipt_enforcement_mode"])
        self.client.force_login(self.student)
        response = self._post("complete")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Receipt link is required", response.json()["error"])

    def test_hard_mode_allows_student_complete_with_valid_receipt(self):
        settings, _ = ParentSettings.objects.get_or_create(user=self.parent)
        settings.receipt_enforcement_mode = "hard"
        settings.save(update_fields=["receipt_enforcement_mode"])
        LessonLog.objects.create(
            scheduled_lesson=self.sl,
            completion_receipt_url="https://www.thenational.academy/teachers/programmes/science-secondary-ks3/units/intro/lessons/update-test-lesson/results/abc123/share",
            completion_receipt_meta={"title_match": True},
        )
        self.client.force_login(self.student)
        response = self._post("complete")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "complete")

    # ---------- mark skipped ----------

    def test_mark_skipped_returns_success_json(self):
        self.client.force_login(self.student)
        response = self._post("skipped")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["status"], "skipped")

    def test_mark_skipped_does_not_set_completed_at(self):
        self.client.force_login(self.student)
        self._post("skipped")
        log = LessonLog.objects.get(scheduled_lesson=self.sl)
        self.assertIsNone(log.completed_at)

    def test_mark_overdue_returns_success_json(self):
        self.client.force_login(self.student)
        response = self._post("overdue")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["status"], "overdue")

    # ---------- idempotency / update existing log ----------

    def test_status_update(self):
        """Posting complete then skipped should update the same LessonLog row."""
        self.client.force_login(self.student)
        self._post("complete")
        self._post("skipped")
        # Only one LessonLog row should exist
        logs = LessonLog.objects.filter(scheduled_lesson=self.sl)
        self.assertEqual(logs.count(), 1)
        self.assertEqual(logs.first().status, "skipped")

    # ---------- response JSON shape ----------

    def test_response_contains_message_key(self):
        self.client.force_login(self.student)
        data = self._post("complete").json()
        self.assertIn("message", data)

    def test_skip_response_message(self):
        self.client.force_login(self.student)
        data = self._post("skipped").json()
        self.assertIn("message", data)
        self.assertIn("skip", data["message"].lower())


class LessonMasteryUpdateTests(TestCase):
    """Tests for S2.6 update_mastery_view POST endpoint."""

    MASTERY_URL = "tracker:lesson_mastery"

    def setUp(self):
        self.parent = _make_parent(username="mast_parent")
        self.student = _make_student(username="mast_student")
        self.child = _make_child(self.parent, student_user=self.student)
        self.lesson = _make_lesson(title="Mastery Test Lesson")
        self.enrolled = _make_enrolled_subject(self.child, subject_name="History")
        self.monday = datetime.date.fromisocalendar(2026, 13, 1)
        self.sl = _make_scheduled_lesson(
            self.child, self.lesson, self.enrolled, self.monday
        )

    def _url(self, pk=None):
        return reverse(self.MASTERY_URL, kwargs={"scheduled_id": pk or self.sl.pk})

    def _post(self, mastery, pk=None):
        return self.client.post(
            self._url(pk), {"mastery": mastery}, HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )

    # ---------- access ----------

    def test_unauthenticated_redirects(self):
        response = self._post("green")
        self.assertEqual(response.status_code, 302)

    def test_parent_can_update_mastery(self):
        self.client.force_login(self.parent)
        response = self._post("green")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["mastery"], "green")

    def test_get_method_not_allowed(self):
        self.client.force_login(self.student)
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 405)

    def test_other_student_gets_403(self):
        other_student = _make_student(username="mast_other")
        _make_child(self.parent, student_user=other_student)
        self.client.force_login(other_student)
        response = self._post("green")
        self.assertEqual(response.status_code, 403)

    def test_student_without_child_profile_gets_403(self):
        bare = User.objects.create_user(username="mast_bare", password="Pass!")
        UserProfile.objects.create(user=bare, role="student")
        self.client.force_login(bare)
        response = self._post("green")
        self.assertEqual(response.status_code, 403)

    # ---------- validation ----------

    def test_invalid_mastery_returns_400(self):
        self.client.force_login(self.student)
        response = self._post("excellent")
        self.assertEqual(response.status_code, 400)

    def test_unset_mastery_value_returns_400(self):
        self.client.force_login(self.student)
        response = self._post("unset")
        self.assertEqual(response.status_code, 400)

    # ---------- green / amber / red ----------

    def test_green_returns_success_json(self):
        self.client.force_login(self.student)
        response = self._post("green")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["mastery"], "green")

    def test_amber_returns_success_json(self):
        self.client.force_login(self.student)
        response = self._post("amber")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["mastery"], "amber")

    def test_red_returns_success_json(self):
        self.client.force_login(self.student)
        response = self._post("red")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["mastery"], "red")

    # ---------- persistence ----------

    def test_mastery_saves_to_lesson_log(self):
        self.client.force_login(self.student)
        self._post("green")
        log = LessonLog.objects.get(scheduled_lesson=self.sl)
        self.assertEqual(log.mastery, "green")

    def test_creates_lesson_log_when_none_exists(self):
        self.client.force_login(self.student)
        self.assertFalse(LessonLog.objects.filter(scheduled_lesson=self.sl).exists())
        self._post("amber")
        self.assertTrue(LessonLog.objects.filter(scheduled_lesson=self.sl).exists())

    def test_updates_existing_lesson_log(self):
        LessonLog.objects.create(scheduled_lesson=self.sl, mastery="green")
        self.client.force_login(self.student)
        self._post("red")
        log = LessonLog.objects.get(scheduled_lesson=self.sl)
        self.assertEqual(log.mastery, "red")

    def test_mastery_changeable_only_one_log_row(self):
        self.client.force_login(self.student)
        self._post("green")
        self._post("amber")
        logs = LessonLog.objects.filter(scheduled_lesson=self.sl)
        self.assertEqual(logs.count(), 1)
        self.assertEqual(logs.first().mastery, "amber")


class LessonNotesTests(TestCase):
    """Tests for S2.7 save_notes_view POST endpoint."""

    NOTES_URL = "tracker:lesson_notes"

    def setUp(self):
        self.parent = _make_parent(username="notes_parent")
        self.student = _make_student(username="notes_student")
        self.child = _make_child(self.parent, student_user=self.student)
        self.lesson = _make_lesson(title="Notes Test Lesson")
        self.enrolled = _make_enrolled_subject(self.child, subject_name="English")
        self.monday = datetime.date.fromisocalendar(2026, 14, 1)
        self.sl = _make_scheduled_lesson(
            self.child, self.lesson, self.enrolled, self.monday
        )

    def _url(self, pk=None):
        return reverse(self.NOTES_URL, kwargs={"scheduled_id": pk or self.sl.pk})

    def _post(self, notes, pk=None):
        return self.client.post(
            self._url(pk), {"notes": notes}, HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )

    # ---------- access ----------

    def test_unauthenticated_redirects(self):
        response = self._post("hello")
        self.assertEqual(response.status_code, 302)

    def test_parent_can_save_notes(self):
        self.client.force_login(self.parent)
        response = self._post("hello")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["student_notes"], "hello")

    def test_get_method_not_allowed(self):
        self.client.force_login(self.student)
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 405)

    def test_other_student_gets_403(self):
        other_student = _make_student(username="notes_other")
        _make_child(self.parent, student_user=other_student)
        self.client.force_login(other_student)
        response = self._post("hello")
        self.assertEqual(response.status_code, 403)

    def test_student_without_child_profile_gets_403(self):
        bare = User.objects.create_user(username="notes_bare", password="Pass!")
        UserProfile.objects.create(user=bare, role="student")
        self.client.force_login(bare)
        response = self._post("hello")
        self.assertEqual(response.status_code, 403)

    # ---------- validation ----------

    def test_notes_over_1000_chars_returns_400(self):
        self.client.force_login(self.student)
        response = self._post("x" * 1001)
        self.assertEqual(response.status_code, 400)

    def test_notes_exactly_1000_chars_is_accepted(self):
        self.client.force_login(self.student)
        response = self._post("x" * 1000)
        self.assertEqual(response.status_code, 200)

    def test_empty_notes_is_valid(self):
        self.client.force_login(self.student)
        response = self._post("")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])

    # ---------- persistence ----------

    def test_notes_save_to_lesson_log(self):
        self.client.force_login(self.student)
        self._post("Great session today!")
        log = LessonLog.objects.get(scheduled_lesson=self.sl)
        self.assertEqual(log.student_notes, "Great session today!")

    def test_creates_lesson_log_when_none_exists(self):
        self.client.force_login(self.student)
        self.assertFalse(LessonLog.objects.filter(scheduled_lesson=self.sl).exists())
        self._post("first note")
        self.assertTrue(LessonLog.objects.filter(scheduled_lesson=self.sl).exists())

    def test_updates_existing_lesson_log_notes(self):
        LessonLog.objects.create(scheduled_lesson=self.sl, student_notes="old note")
        self.client.force_login(self.student)
        self._post("new note")
        log = LessonLog.objects.get(scheduled_lesson=self.sl)
        self.assertEqual(log.student_notes, "new note")

    def test_second_post_keeps_single_log_row(self):
        self.client.force_login(self.student)
        self._post("first")
        self._post("second")
        self.assertEqual(LessonLog.objects.filter(scheduled_lesson=self.sl).count(), 1)

    def test_response_contains_student_notes_key(self):
        self.client.force_login(self.student)
        data = self._post("test").json()
        self.assertIn("student_notes", data)

    # ---------- notes appear in lesson detail ----------

    def test_saved_notes_appear_in_detail_response(self):
        LessonLog.objects.create(
            scheduled_lesson=self.sl,
            student_notes="saved note",
            updated_by=self.student,
        )
        self.client.force_login(self.student)
        response = self.client.get(
            reverse("tracker:lesson_detail", kwargs={"scheduled_id": self.sl.pk})
        )
        self.assertEqual(response.json()["student_notes"], "saved note")


class LessonRescheduleTests(TestCase):
    """Tests for S2.8 reschedule_lesson_view POST endpoint."""

    RESCHEDULE_URL = "tracker:lesson_reschedule"

    def setUp(self):
        self.parent = _make_parent(username="rsch_parent")
        self.student = _make_student(username="rsch_student")
        self.child = _make_child(self.parent, student_user=self.student)
        self.lesson = _make_lesson(title="Reschedule Test Lesson")
        self.enrolled = _make_enrolled_subject(self.child, subject_name="Geography")
        self.monday = datetime.date.fromisocalendar(2026, 15, 1)
        self.sl = _make_scheduled_lesson(
            self.child, self.lesson, self.enrolled, self.monday
        )

    def _url(self, pk=None):
        return reverse(self.RESCHEDULE_URL, kwargs={"scheduled_id": pk or self.sl.pk})

    def _post(self, new_date, pk=None):
        return self.client.post(
            self._url(pk),
            {"new_date": new_date},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    # ---------- access ----------

    def test_unauthenticated_redirects(self):
        response = self._post("2030-01-01")
        self.assertEqual(response.status_code, 302)

    def test_parent_can_reschedule(self):
        self.client.force_login(self.parent)
        response = self._post("2030-01-01")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["new_date"], "2030-01-01")

    def test_get_method_not_allowed(self):
        self.client.force_login(self.student)
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 405)

    def test_other_student_gets_403(self):
        other_student = _make_student(username="rsch_other")
        _make_child(self.parent, student_user=other_student)
        self.client.force_login(other_student)
        response = self._post("2030-01-01")
        self.assertEqual(response.status_code, 403)

    def test_student_without_child_profile_gets_403(self):
        bare = User.objects.create_user(username="rsch_bare", password="Pass!")
        UserProfile.objects.create(user=bare, role="student")
        self.client.force_login(bare)
        response = self._post("2030-01-01")
        self.assertEqual(response.status_code, 403)

    # ---------- validation ----------

    def test_past_date_returns_400(self):
        self.client.force_login(self.student)
        response = self._post("2000-01-01")
        self.assertEqual(response.status_code, 400)

    def test_today_date_returns_400(self):
        self.client.force_login(self.student)
        today = datetime.date.today().isoformat()
        response = self._post(today)
        self.assertEqual(response.status_code, 400)

    def test_invalid_date_format_returns_400(self):
        self.client.force_login(self.student)
        response = self._post("not-a-date")
        self.assertEqual(response.status_code, 400)

    # ---------- happy path ----------

    def test_future_date_returns_200_success(self):
        self.client.force_login(self.student)
        response = self._post("2030-06-15")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])

    def test_reschedule_updates_scheduled_lesson_date(self):
        self.client.force_login(self.student)
        self._post("2030-06-15")
        self.sl.refresh_from_db()
        self.assertEqual(self.sl.scheduled_date, datetime.date(2030, 6, 15))

    def test_reschedule_creates_lesson_log_when_none(self):
        self.client.force_login(self.student)
        self.assertFalse(LessonLog.objects.filter(scheduled_lesson=self.sl).exists())
        self._post("2030-06-15")
        self.assertTrue(LessonLog.objects.filter(scheduled_lesson=self.sl).exists())

    def test_reschedule_sets_rescheduled_to_on_log(self):
        self.client.force_login(self.student)
        self._post("2030-06-15")
        log = LessonLog.objects.get(scheduled_lesson=self.sl)
        self.assertEqual(log.rescheduled_to, datetime.date(2030, 6, 15))

    def test_reschedule_updates_existing_log(self):
        LessonLog.objects.create(
            scheduled_lesson=self.sl, rescheduled_to=datetime.date(2029, 1, 1)
        )
        self.client.force_login(self.student)
        self._post("2030-06-15")
        log = LessonLog.objects.get(scheduled_lesson=self.sl)
        self.assertEqual(log.rescheduled_to, datetime.date(2030, 6, 15))

    def test_response_contains_new_date(self):
        self.client.force_login(self.student)
        data = self._post("2030-06-15").json()
        self.assertEqual(data["new_date"], "2030-06-15")


class LessonModalEnhancementEndpointTests(TestCase):
    """Tests for lesson receipt/comment/edit/delete endpoint additions."""

    def setUp(self):
        self.parent = _make_parent(username="enh_parent")
        self.student = _make_student(username="enh_student")
        self.child = _make_child(self.parent, student_user=self.student)
        self.lesson = _make_lesson(title="Enhancement Lesson")
        self.enrolled = _make_enrolled_subject(self.child, subject_name="Science")
        self.sl = _make_scheduled_lesson(
            self.child,
            self.lesson,
            self.enrolled,
            datetime.date.today() + datetime.timedelta(days=7),
        )

    def _receipt_url(self, pk=None):
        return reverse(
            "tracker:lesson_receipt", kwargs={"scheduled_id": pk or self.sl.pk}
        )

    def _comment_url(self, pk=None):
        return reverse(
            "tracker:lesson_comment", kwargs={"scheduled_id": pk or self.sl.pk}
        )

    def _edit_url(self, pk=None):
        return reverse("tracker:lesson_edit", kwargs={"scheduled_id": pk or self.sl.pk})

    def _delete_url(self, pk=None):
        return reverse(
            "tracker:lesson_delete", kwargs={"scheduled_id": pk or self.sl.pk}
        )

    def test_parent_can_save_receipt_metadata(self):
        self.client.force_login(self.parent)
        response = self.client.post(
            self._receipt_url(),
            {
                "receipt_url": "https://www.thenational.academy/teachers/programmes/english-secondary-ks3/units/intro/lessons/enhancement-lesson/results/abc123/share"
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["completion_receipt_meta"]["result_token"], "abc123")

    def test_receipt_save_marks_lesson_complete(self):
        self.client.force_login(self.student)
        response = self.client.post(
            self._receipt_url(),
            {
                "receipt_url": "https://www.thenational.academy/teachers/programmes/english-secondary-ks3/units/intro/lessons/enhancement-lesson/results/receipt777/share"
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "complete")
        log = LessonLog.objects.get(scheduled_lesson=self.sl)
        self.assertEqual(log.status, "complete")
        self.assertTrue(log.completion_receipt_meta.get("title_match"))

    def test_invalid_receipt_url_rejected(self):
        self.client.force_login(self.student)
        response = self.client.post(
            self._receipt_url(),
            {"receipt_url": "not-a-url"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 400)

    def test_receipt_link_mismatch_rejected(self):
        self.client.force_login(self.student)
        response = self.client.post(
            self._receipt_url(),
            {
                "receipt_url": "https://www.thenational.academy/teachers/programmes/english-secondary-ks3/units/intro/lessons/different-lesson/results/abc123/share"
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("does not match", response.json()["error"])

    def test_parent_can_add_comment(self):
        self.client.force_login(self.parent)
        response = self.client.post(
            self._comment_url(),
            {"body": "Great effort this week."},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            LessonComment.objects.filter(scheduled_lesson=self.sl).count(), 1
        )
        self.assertEqual(response.json()["comments_count"], 1)

    def test_edit_updates_scheduled_date(self):
        self.client.force_login(self.student)
        new_date = (datetime.date.today() + datetime.timedelta(days=21)).isoformat()
        response = self.client.post(
            self._edit_url(),
            {"scheduled_date": new_date, "order_on_day": "2"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.sl.refresh_from_db()
        self.assertEqual(self.sl.scheduled_date.isoformat(), new_date)
        self.assertEqual(self.sl.order_on_day, 2)

    def test_parent_can_delete_scheduled_lesson(self):
        self.client.force_login(self.parent)
        response = self.client.post(
            self._delete_url(),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ScheduledLesson.objects.filter(pk=self.sl.pk).exists())


class ParentCalendarTests(TestCase):
    """Tests for S2.9 parent_calendar_view — read-only calendar for parents."""

    def setUp(self):
        self.parent = _make_parent(username="pcal_parent")
        self.other_parent = _make_parent(username="pcal_other_parent")
        self.student = _make_student(username="pcal_student")
        self.child = _make_child(self.parent, student_user=self.student)
        self.lesson = _make_lesson(title="Parent View Test Lesson")
        self.enrolled = _make_enrolled_subject(self.child, subject_name="Science")
        self.monday = datetime.date.fromisocalendar(2026, 16, 1)
        self.sl = _make_scheduled_lesson(
            self.child, self.lesson, self.enrolled, self.monday
        )

    def _url(self, child_id=None, year=None, week=None):
        child_id = child_id or self.child.pk
        if year is not None and week is not None:
            return reverse(
                "tracker:parent_calendar_week",
                kwargs={"child_id": child_id, "year": year, "week": week},
            )
        return reverse("tracker:parent_calendar", kwargs={"child_id": child_id})

    # ---------- access ----------

    def test_unauthenticated_redirects(self):
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 302)

    def test_student_role_blocked(self):
        self.client.force_login(self.student)
        response = self.client.get(self._url())
        self.assertRedirects(response, "/", fetch_redirect_response=False)

    def test_other_parent_gets_403(self):
        self.client.force_login(self.other_parent)
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 403)

    def test_owner_parent_gets_200(self):
        self.client.force_login(self.parent)
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)

    # ---------- content ----------

    def test_uses_calendar_template(self):
        self.client.force_login(self.parent)
        response = self.client.get(self._url())
        self.assertTemplateUsed(response, "tracker/calendar.html")

    def test_is_readonly_in_context(self):
        self.client.force_login(self.parent)
        response = self.client.get(self._url())
        self.assertTrue(response.context["is_readonly"])

    def test_child_name_in_context(self):
        self.client.force_login(self.parent)
        response = self.client.get(self._url())
        self.assertEqual(response.context["child_name"], self.child.first_name)

    def test_lesson_action_buttons_rendered(self):
        self.client.force_login(self.parent)
        response = self.client.get(self._url())
        content = response.content.decode()
        self.assertIn("modal-btn-complete", content)
        self.assertIn("modal-btn-reschedule", content)
        self.assertNotIn("modal-btn-skip", content)

    def test_notes_and_mastery_controls_rendered(self):
        self.client.force_login(self.parent)
        response = self.client.get(self._url())
        content = response.content.decode()
        self.assertIn("modal-btn-save-notes", content)
        self.assertIn('id="modal-notes"', content)

    def test_lesson_appears_in_calendar(self):
        self.client.force_login(self.parent)
        response = self.client.get(self._url(year=2026, week=16))
        self.assertContains(response, self.lesson.lesson_title)

    # ---------- week navigation ----------

    def test_week_navigation_returns_200(self):
        self.client.force_login(self.parent)
        response = self.client.get(self._url(year=2026, week=16))
        self.assertEqual(response.status_code, 200)

    def test_prev_next_urls_use_parent_calendar_route(self):
        self.client.force_login(self.parent)
        response = self.client.get(self._url(year=2026, week=16))
        content = response.content.decode()
        self.assertIn(f"/parent/calendar/{self.child.pk}/", content)

    def test_student_calendar_unaffected_for_student(self):
        """Student calendar is still accessible and not read-only."""
        self.client.force_login(self.student)
        response = self.client.get(reverse("tracker:calendar"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context.get("is_readonly", False))

    def test_nonexistent_child_returns_404(self):
        self.client.force_login(self.parent)
        response = self.client.get(self._url(child_id=99999))
        self.assertEqual(response.status_code, 404)


class CalendarSemanticsCopyTests(TestCase):
    """Ensure calendar clarifies manual assignments vs scheduled lessons."""

    def setUp(self):
        self.parent = _make_parent(username="sem_parent")
        self.student = _make_student(username="sem_student")
        self.child = _make_child(self.parent, student_user=self.student)
        self.client.force_login(self.student)

        monday = datetime.date.fromisocalendar(2026, 20, 1)
        lesson = _make_lesson(title="Semantics Lesson")
        enrolled_subject = _make_enrolled_subject(self.child, subject_name="Maths")
        _make_scheduled_lesson(self.child, lesson, enrolled_subject, monday)

        course = Course.objects.create(
            parent=self.parent,
            name="Math Course",
            duration_weeks=12,
            frequency_days=5,
        )
        assignment_type = AssignmentType.objects.create(
            course=course,
            name="Homework",
            color="#9ca3af",
            is_hidden=False,
            weight=0,
            order=0,
        )
        enrollment = course.enrollments.create(
            child=self.child,
            start_date=monday,
            days_of_week=[0, 1, 2, 3, 4],
            status="active",
        )
        template = CourseAssignmentTemplate.objects.create(
            course=course,
            assignment_type=assignment_type,
            name="Worksheet",
            due_offset_days=0,
            order=0,
        )
        plan_item = AssignmentPlanItem.objects.create(
            course=course,
            template=template,
            week_number=1,
            day_number=1,
            due_in_days=0,
            order=0,
        )
        StudentAssignment.objects.create(
            enrollment=enrollment,
            plan_item=plan_item,
            due_date=monday,
            status="pending",
        )

    def test_calendar_renders_assignment_and_lesson_section_labels(self):
        response = self.client.get(
            reverse("tracker:calendar_week", kwargs={"year": 2026, "week": 20})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Assignments (manual course plan)")
        self.assertContains(response, "Lessons (Oak/custom schedule)")
        self.assertContains(
            response,
            "Scheduled from Course Planning timeline.",
        )


class EvidenceUploadTests(TestCase):
    """Tests for S2.10 upload_evidence_view POST endpoint."""

    UPLOAD_URL = "tracker:lesson_upload"

    def setUp(self):
        self.parent = _make_parent(username="ev_parent")
        self.student = _make_student(username="ev_student")
        self.child = _make_child(self.parent, student_user=self.student)
        self.lesson = _make_lesson(title="Evidence Test Lesson")
        self.enrolled = _make_enrolled_subject(self.child, subject_name="Art")
        self.monday = datetime.date.fromisocalendar(2026, 17, 1)
        self.sl = _make_scheduled_lesson(
            self.child, self.lesson, self.enrolled, self.monday
        )

    def _url(self, pk=None):
        return reverse(self.UPLOAD_URL, kwargs={"scheduled_id": pk or self.sl.pk})

    def _post(self, file_name="test.png", content_type="image/png", pk=None):
        f = SimpleUploadedFile(
            file_name, b"fake file content", content_type=content_type
        )
        return self.client.post(
            self._url(pk), {"file": f}, HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )

    # ---------- access ----------

    def test_unauthenticated_redirects(self):
        response = self._post()
        self.assertEqual(response.status_code, 302)

    def test_parent_can_upload_evidence(self):
        self.client.force_login(self.parent)
        with patch("cloudinary.uploader.upload", return_value=_FAKE_CLOUDINARY):
            response = self._post()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])

    def test_get_method_not_allowed(self):
        self.client.force_login(self.student)
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 405)

    def test_other_student_gets_403(self):
        other_student = _make_student(username="ev_other")
        _make_child(self.parent, student_user=other_student)
        self.client.force_login(other_student)
        response = self._post()
        self.assertEqual(response.status_code, 403)

    def test_student_without_child_profile_gets_403(self):
        bare = User.objects.create_user(username="ev_bare", password="Pass!")
        UserProfile.objects.create(user=bare, role="student")
        self.client.force_login(bare)
        response = self._post()
        self.assertEqual(response.status_code, 403)

    # ---------- validation ----------

    def test_no_file_returns_400(self):
        self.client.force_login(self.student)
        response = self.client.post(
            self._url(), {}, HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )
        self.assertEqual(response.status_code, 400)

    def test_invalid_type_exe_returns_400(self):
        self.client.force_login(self.student)
        response = self._post(
            file_name="malware.exe", content_type="application/octet-stream"
        )
        self.assertEqual(response.status_code, 400)

    # ---------- happy path (Cloudinary upload mocked) ----------

    def test_image_upload_returns_200_success(self):
        self.client.force_login(self.student)
        with patch("cloudinary.uploader.upload", return_value=_FAKE_CLOUDINARY):
            response = self._post()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])

    def test_pdf_upload_returns_200(self):
        self.client.force_login(self.student)
        with patch("cloudinary.uploader.upload", return_value=_FAKE_CLOUDINARY):
            response = self._post(file_name="doc.pdf", content_type="application/pdf")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])

    def test_creates_lesson_log_when_none(self):
        self.client.force_login(self.student)
        self.assertFalse(LessonLog.objects.filter(scheduled_lesson=self.sl).exists())
        with patch("cloudinary.uploader.upload", return_value=_FAKE_CLOUDINARY):
            self._post()
        self.assertTrue(LessonLog.objects.filter(scheduled_lesson=self.sl).exists())

    def test_creates_evidence_file_record(self):
        self.client.force_login(self.student)
        with patch("cloudinary.uploader.upload", return_value=_FAKE_CLOUDINARY):
            self._post()
        log = LessonLog.objects.get(scheduled_lesson=self.sl)
        self.assertEqual(log.evidence_files.count(), 1)

    def test_reuses_existing_lesson_log(self):
        existing_log = LessonLog.objects.create(scheduled_lesson=self.sl)
        self.client.force_login(self.student)
        with patch("cloudinary.uploader.upload", return_value=_FAKE_CLOUDINARY):
            self._post()
        self.assertEqual(LessonLog.objects.filter(scheduled_lesson=self.sl).count(), 1)
        existing_log.refresh_from_db()
        self.assertEqual(existing_log.evidence_files.count(), 1)

    def test_response_contains_evidence_count(self):
        self.client.force_login(self.student)
        with patch("cloudinary.uploader.upload", return_value=_FAKE_CLOUDINARY):
            data = self._post().json()
        self.assertIn("evidence_count", data)
        self.assertEqual(data["evidence_count"], 1)

    def test_evidence_count_in_detail_view_reflects_uploads(self):
        """lesson_detail_view returns correct evidence_count after upload."""
        log = LessonLog.objects.create(scheduled_lesson=self.sl)
        with patch("cloudinary.uploader.upload", return_value=_FAKE_CLOUDINARY):
            EvidenceFile.objects.create(
                lesson_log=log,
                file="fake/public_id",
                original_filename="test.png",
                uploaded_by=self.student,
            )
        self.client.force_login(self.student)
        response = self.client.get(
            reverse("tracker:lesson_detail", kwargs={"scheduled_id": self.sl.pk})
        )
        self.assertEqual(response.json()["evidence_count"], 1)


class EvidenceDeleteTests(TestCase):
    """Tests for S2.11 delete_evidence_view POST endpoint."""

    DELETE_URL = "tracker:evidence_delete"

    def setUp(self):
        self.parent = _make_parent(username="del_parent")
        self.student = _make_student(username="del_student")
        self.child = _make_child(self.parent, student_user=self.student)
        self.lesson = _make_lesson(title="Delete Evidence Lesson")
        self.enrolled = _make_enrolled_subject(self.child, subject_name="Science")
        self.monday = datetime.date.fromisocalendar(2026, 18, 1)
        self.sl = _make_scheduled_lesson(
            self.child, self.lesson, self.enrolled, self.monday
        )
        self.log = LessonLog.objects.create(scheduled_lesson=self.sl)
        self.evidence = EvidenceFile.objects.create(
            lesson_log=self.log,
            file="fake/del_public_id",
            original_filename="to_delete.png",
            uploaded_by=self.student,
        )

    def _url(self, file_id=None):
        return reverse(self.DELETE_URL, kwargs={"file_id": file_id or self.evidence.pk})

    # ---------- access ----------

    def test_unauthenticated_redirects(self):
        response = self.client.post(self._url())
        self.assertEqual(response.status_code, 302)

    def test_parent_can_delete_child_evidence(self):
        self.client.force_login(self.parent)
        with patch("cloudinary.uploader.destroy", return_value={"result": "ok"}):
            response = self.client.post(self._url())
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])

    def test_get_method_not_allowed(self):
        self.client.force_login(self.student)
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 405)

    def test_other_student_gets_403(self):
        other_student = _make_student(username="del_other")
        _make_child(self.parent, student_user=other_student)
        self.client.force_login(other_student)
        with patch("cloudinary.uploader.destroy", return_value={"result": "ok"}):
            response = self.client.post(self._url())
        self.assertEqual(response.status_code, 403)

    # ---------- happy path ----------

    def test_owner_can_delete_returns_200(self):
        self.client.force_login(self.student)
        with patch("cloudinary.uploader.destroy", return_value={"result": "ok"}):
            response = self.client.post(self._url())
        self.assertEqual(response.status_code, 200)

    def test_delete_removes_db_record(self):
        pk = self.evidence.pk
        self.client.force_login(self.student)
        with patch("cloudinary.uploader.destroy", return_value={"result": "ok"}):
            self.client.post(self._url())
        self.assertFalse(EvidenceFile.objects.filter(pk=pk).exists())

    def test_delete_calls_cloudinary_destroy(self):
        self.client.force_login(self.student)
        with patch(
            "cloudinary.uploader.destroy", return_value={"result": "ok"}
        ) as mock_destroy:
            self.client.post(self._url())
        mock_destroy.assert_called_once()

    def test_response_contains_success_true(self):
        self.client.force_login(self.student)
        with patch("cloudinary.uploader.destroy", return_value={"result": "ok"}):
            data = self.client.post(self._url()).json()
        self.assertTrue(data["success"])

    def test_response_contains_evidence_count(self):
        self.client.force_login(self.student)
        with patch("cloudinary.uploader.destroy", return_value={"result": "ok"}):
            data = self.client.post(self._url()).json()
        self.assertIn("evidence_count", data)

    def test_evidence_count_decrements(self):
        # Add a second file so count goes from 2 → 1
        second = EvidenceFile.objects.create(
            lesson_log=self.log,
            file="fake/second_public_id",
            original_filename="second.png",
            uploaded_by=self.student,
        )
        self.client.force_login(self.student)
        with patch("cloudinary.uploader.destroy", return_value={"result": "ok"}):
            data = self.client.post(self._url()).json()
        self.assertEqual(data["evidence_count"], 1)
        second.delete()  # cleanup

    def test_nonexistent_file_returns_404(self):
        self.client.force_login(self.student)
        response = self.client.post(self._url(file_id=99999))
        self.assertEqual(response.status_code, 404)

    # ---------- lesson_detail evidence_files list ----------

    def test_evidence_files_in_detail_response(self):
        self.client.force_login(self.student)
        response = self.client.get(
            reverse("tracker:lesson_detail", kwargs={"scheduled_id": self.sl.pk})
        )
        self.assertIn("evidence_files", response.json())

    def test_evidence_files_list_contains_filename(self):
        self.client.force_login(self.student)
        response = self.client.get(
            reverse("tracker:lesson_detail", kwargs={"scheduled_id": self.sl.pk})
        )
        files = response.json()["evidence_files"]
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]["filename"], "to_delete.png")

    def test_evidence_files_list_empty_when_none(self):
        # Use a lesson with no log
        new_lesson = _make_lesson(title="Empty Evidence Lesson")
        new_sl = _make_scheduled_lesson(
            self.child,
            new_lesson,
            self.enrolled,
            datetime.date.fromisocalendar(2026, 18, 2),
        )
        self.client.force_login(self.student)
        response = self.client.get(
            reverse("tracker:lesson_detail", kwargs={"scheduled_id": new_sl.pk})
        )
        self.assertEqual(response.json()["evidence_files"], [])


class AssignmentCalendarEndpointTests(TestCase):
    def setUp(self):
        self.parent = _make_parent(username="assign_parent")
        self.student = _make_student(username="assign_student")
        self.child = _make_child(
            self.parent,
            first_name="AssignKid",
            student_user=self.student,
        )

        self.course = Course.objects.create(
            parent=self.parent,
            name="History",
            duration_weeks=10,
            frequency_days=3,
        )
        self.enrollment = self.course.enrollments.create(
            child=self.child,
            start_date=datetime.date(2026, 1, 6),
            days_of_week=[0, 2, 4],
            status="active",
        )
        self.assignment_type = AssignmentType.objects.create(
            course=self.course,
            name="Homework",
            color="#9ca3af",
            order=0,
        )
        self.template = CourseAssignmentTemplate.objects.create(
            course=self.course,
            assignment_type=self.assignment_type,
            name="Essay Draft",
            description="Write a short draft",
            is_graded=True,
            due_offset_days=0,
            order=0,
        )
        self.plan_item = AssignmentPlanItem.objects.create(
            course=self.course,
            template=self.template,
            week_number=1,
            day_number=2,
            due_in_days=0,
            order=0,
            notes="Submit by noon",
        )
        self.assignment = StudentAssignment.objects.create(
            enrollment=self.enrollment,
            plan_item=self.plan_item,
            due_date=datetime.date.today() - datetime.timedelta(days=2),
            status="pending",
        )

    def test_student_can_open_assignment_detail(self):
        self.client.force_login(self.student)
        response = self.client.get(
            reverse(
                "tracker:assignment_detail",
                kwargs={"assignment_id": self.assignment.pk},
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["effective_status"], "overdue")

    def test_parent_can_update_assignment_status_to_done(self):
        self.client.force_login(self.parent)
        response = self.client.post(
            reverse(
                "tracker:assignment_update",
                kwargs={"assignment_id": self.assignment.pk},
            ),
            {"status": "done"},
        )
        self.assertEqual(response.status_code, 200)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, "complete")
        self.assertEqual(response.json()["status"], "done")

    def test_student_done_sets_needs_grading_but_response_is_done(self):
        self.client.force_login(self.student)
        response = self.client.post(
            reverse(
                "tracker:assignment_update",
                kwargs={"assignment_id": self.assignment.pk},
            ),
            {"status": "done"},
        )
        self.assertEqual(response.status_code, 200)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, "needs_grading")
        self.assertEqual(response.json()["status"], "done")

    def test_student_mark_incomplete_becomes_overdue_when_past_due(self):
        self.assignment.status = "complete"
        self.assignment.save(update_fields=["status"])
        self.client.force_login(self.student)
        response = self.client.post(
            reverse(
                "tracker:assignment_update",
                kwargs={"assignment_id": self.assignment.pk},
            ),
            {"status": "incomplete"},
        )
        self.assertEqual(response.status_code, 200)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, "pending")
        self.assertEqual(response.json()["status"], "overdue")


class HomeAssignmentsDashboardTests(TestCase):
    URL = "tracker:home_assignments"

    def setUp(self):
        self.parent = _make_parent(username="home_parent")
        self.student = _make_student(username="home_student")
        self.child = _make_child(
            self.parent,
            first_name="Amina",
            student_user=self.student,
        )

        self.teacher = User.objects.create_user(
            username="home_teacher", password="TestPass123!"
        )
        UserProfile.objects.create(user=self.teacher, role="teacher")

        self.course = Course.objects.create(
            parent=self.parent,
            name="Mathematics",
            duration_weeks=10,
            frequency_days=3,
        )
        self.enrollment = self.course.enrollments.create(
            child=self.child,
            start_date=datetime.date(2026, 1, 6),
            days_of_week=[0, 2, 4],
            status="active",
        )
        self.assignment_type = AssignmentType.objects.create(
            course=self.course,
            name="Quiz",
            color="#9ca3af",
            order=0,
        )
        self.template = CourseAssignmentTemplate.objects.create(
            course=self.course,
            assignment_type=self.assignment_type,
            name="Algebra Quiz",
            description="Answer all questions",
            is_graded=True,
            due_offset_days=0,
            order=0,
        )
        self.plan_item = AssignmentPlanItem.objects.create(
            course=self.course,
            template=self.template,
            week_number=1,
            day_number=2,
            due_in_days=0,
            order=0,
            notes="Bring a calculator",
        )
        self.assignment = StudentAssignment.objects.create(
            enrollment=self.enrollment,
            plan_item=self.plan_item,
            due_date=datetime.date.today(),
            status="pending",
        )
        self.enrolled_subject = _make_enrolled_subject(
            self.child,
            subject_name="Maths",
        )
        self.lesson = _make_lesson(subject="Maths", title="Fractions Intro")
        self.scheduled_lesson = _make_scheduled_lesson(
            self.child,
            self.lesson,
            self.enrolled_subject,
            datetime.date.today(),
        )

    def test_home_assignments_prefers_new_plan_item_display_data(self):
        plan_item = PlanItem.objects.create(
            course=self.course,
            item_type=PlanItem.ITEM_TYPE_ASSIGNMENT,
            week_number=1,
            day_number=2,
            name="Unified Algebra Quiz",
            description="Use PlanItem description",
        )
        self.assignment.new_plan_item = plan_item
        self.assignment.save(update_fields=["new_plan_item"])

        self.client.force_login(self.parent)
        response = self.client.get(reverse(self.URL) + "?tab=assignments")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Unified Algebra Quiz")
        self.assertContains(response, "Use PlanItem description")

    def test_home_activities_include_legacy_only_progress_rows(self):
        activity_template = CourseAssignmentTemplate.objects.create(
            course=self.course,
            assignment_type=None,
            item_kind="activity",
            name="Legacy Activity",
        )
        activity_plan = AssignmentPlanItem.objects.create(
            course=self.course,
            template=activity_template,
            week_number=1,
            day_number=2,
        )
        ActivityProgress.objects.create(
            enrollment=self.enrollment,
            plan_item=activity_plan,
            status="pending",
        )

        self.client.force_login(self.parent)
        response = self.client.get(reverse(self.URL) + "?tab=activities")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Legacy Activity")

    def test_parent_sees_assignments_dashboard(self):
        self.client.force_login(self.parent)
        response = self.client.get(reverse(self.URL))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "tracker/home_assignments.html")
        self.assertContains(response, "Lessons")
        self.assertContains(response, "Fractions Intro")

        assignments_tab = self.client.get(reverse(self.URL), {"tab": "assignments"})
        self.assertContains(assignments_tab, "Algebra Quiz")

    def test_selected_lesson_renders_details_panel(self):
        self.client.force_login(self.parent)
        response = self.client.get(
            reverse(self.URL),
            {
                "tab": "lessons",
                "selected_lesson": self.scheduled_lesson.pk,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Lesson Details")
        self.assertContains(response, "Fractions Intro")

    def test_selected_assignment_renders_details_panel(self):
        self.client.force_login(self.parent)
        response = self.client.get(
            reverse(self.URL),
            {"tab": "assignments", "selected": self.assignment.pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Assignment Details")
        self.assertContains(response, "Algebra Quiz")
        self.assertContains(response, "Bring a calculator")

    def test_student_only_sees_own_assignments(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse(self.URL), {"tab": "assignments"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Algebra Quiz")

    def test_status_filter_done_hides_pending_assignment(self):
        self.client.force_login(self.parent)
        response = self.client.get(
            reverse(self.URL),
            {"tab": "assignments", "status": "done", "hide_completed": "0"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No assignments match your current filters")

    def test_teacher_has_access_to_home_dashboard(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse(self.URL))
        self.assertEqual(response.status_code, 200)

    def test_parent_can_post_comment_from_home(self):
        self.client.force_login(self.parent)
        response = self.client.post(
            reverse(
                "tracker:home_assignment_comment_create",
                kwargs={"assignment_id": self.assignment.pk},
            ),
            {
                "comment": "Please upload your work by tonight.",
                "next": f"/home/?selected={self.assignment.pk}",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            AssignmentComment.objects.filter(
                assignment=self.assignment,
                author=self.parent,
                body="Please upload your work by tonight.",
            ).exists()
        )

    def test_student_can_upload_submission_from_home(self):
        self.client.force_login(self.student)
        upload = SimpleUploadedFile(
            "answer.pdf",
            b"pdf bytes",
            content_type="application/pdf",
        )
        response = self.client.post(
            reverse(
                "tracker:home_assignment_submission_upload",
                kwargs={"assignment_id": self.assignment.pk},
            ),
            {
                "submission": upload,
                "next": f"/home/?selected={self.assignment.pk}",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            AssignmentSubmission.objects.filter(
                assignment=self.assignment,
                uploaded_by=self.student,
                original_name="answer.pdf",
            ).exists()
        )

    def test_student_cannot_grade_from_home(self):
        self.client.force_login(self.student)
        response = self.client.post(
            reverse(
                "tracker:home_assignment_grade",
                kwargs={"assignment_id": self.assignment.pk},
            ),
            {
                "score": "80",
                "points_available": "100",
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_parent_can_grade_from_home(self):
        self.client.force_login(self.parent)
        response = self.client.post(
            reverse(
                "tracker:home_assignment_grade",
                kwargs={"assignment_id": self.assignment.pk},
            ),
            {
                "score": "85",
                "points_available": "100",
                "score_percent": "85",
                "status": "complete",
                "grading_notes": "Great progress.",
                "next": f"/home/?selected={self.assignment.pk}",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assignment.refresh_from_db()
        self.assertEqual(str(self.assignment.score), "85.00")
        self.assertEqual(self.assignment.status, "complete")
        self.assertEqual(self.assignment.grading_notes, "Great progress.")

    def test_student_mark_complete_persists_needs_grading_in_home(self):
        self.client.force_login(self.student)
        response = self.client.post(
            reverse(
                "tracker:home_assignment_status",
                kwargs={"assignment_id": self.assignment.pk},
            ),
            {
                "status": "done",
                "next": reverse(self.URL),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, "needs_grading")

    def test_student_home_still_shows_completed_for_needs_grading(self):
        self.assignment.status = "needs_grading"
        self.assignment.save(update_fields=["status"])
        self.client.force_login(self.student)
        response = self.client.get(
            reverse(self.URL),
            {"tab": "assignments", "selected": self.assignment.pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Completed")
