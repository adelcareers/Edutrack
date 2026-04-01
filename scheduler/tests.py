"""Tests for the scheduler app — S1.4, S1.5 & S1.6."""

import datetime
import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserProfile
from courses.models import (
    Course,
    CourseEnrollment,
    CourseSubjectConfig,
    CourseSubjectScheduleSlot,
)
from curriculum.models import Lesson
from planning.models import PlanItem
from scheduler.models import Child, EnrolledSubject, ScheduledLesson
from tracker.models import LessonLog


def _make_parent(username="parent1", password="TestPass123!"):
    """Helper: create a parent User + UserProfile."""
    user = User.objects.create_user(username=username, password=password)
    UserProfile.objects.create(user=user, role="parent")
    return user


def _make_child(parent, first_name="Alice"):
    """Helper: create a minimal Child record for a parent."""
    return Child.objects.create(
        parent=parent,
        first_name=first_name,
        birth_month=1,
        birth_year=2015,
        school_year="Year 5",
        academic_year_start=datetime.date(2025, 9, 1),
    )


CREATE_URL = "scheduler:create_student_login"


class CreateStudentLoginAccessTests(TestCase):
    """Gate tests: who can reach the page."""

    def setUp(self):
        self.parent = _make_parent()
        self.child = _make_child(self.parent)
        self.url = reverse(CREATE_URL, kwargs={"child_id": self.child.pk})

    def test_unauthenticated_redirects_to_login(self):
        response = self.client.get(self.url)
        self.assertRedirects(response, f"/accounts/login/?next={self.url}")

    def test_student_role_blocked(self):
        student_user = User.objects.create_user(username="stu", password="Pass123!")
        UserProfile.objects.create(user=student_user, role="student")
        self.client.force_login(student_user)
        response = self.client.get(self.url)
        self.assertRedirects(response, "/", fetch_redirect_response=False)

    def test_parent_can_access_own_child(self):
        self.client.force_login(self.parent)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "scheduler/create_student_login.html")

    def test_parent_cannot_access_other_parents_child(self):
        other_parent = _make_parent(username="parent2")
        self.client.force_login(other_parent)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)


class CreateStudentLoginPostTests(TestCase):
    """Form submission scenarios."""

    def setUp(self):
        self.parent = _make_parent()
        self.child = _make_child(self.parent)
        self.url = reverse(CREATE_URL, kwargs={"child_id": self.child.pk})
        self.client.force_login(self.parent)

    def test_valid_post_creates_user_and_profile(self):
        response = self.client.post(
            self.url,
            {
                "email": "alice_student@example.com",
                "password1": "SecurePass99!",
                "password2": "SecurePass99!",
            },
        )
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        student_user = User.objects.get(username="alice_student@example.com")
        self.assertEqual(student_user.profile.role, "student")
        self.assertEqual(student_user.email, "alice_student@example.com")

    def test_valid_post_links_child_student_user(self):
        self.client.post(
            self.url,
            {
                "email": "alice_student@example.com",
                "password1": "SecurePass99!",
                "password2": "SecurePass99!",
            },
        )
        self.child.refresh_from_db()
        self.assertIsNotNone(self.child.student_user)
        self.assertEqual(
            self.child.student_user.username, "alice_student@example.com"
        )

    def test_duplicate_email_shows_error(self):
        User.objects.create_user(
            username="taken@example.com",
            email="taken@example.com",
            password="Pass123!",
        )
        response = self.client.post(
            self.url,
            {
                "email": "taken@example.com",
                "password1": "SecurePass99!",
                "password2": "SecurePass99!",
            },
        )
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertTrue(form.errors)
        self.assertIn("email", form.errors)

    def test_child_with_existing_student_user_redirects(self):
        existing = User.objects.create_user(
            username="existing_stu", password="Pass123!"
        )
        UserProfile.objects.create(user=existing, role="student")
        self.child.student_user = existing
        self.child.save()
        response = self.client.get(self.url)
        self.assertRedirects(response, "/", fetch_redirect_response=False)

    def test_student_can_log_in_after_creation(self):
        self.client.post(
            self.url,
            {
                "email": "alice_student@example.com",
                "password1": "SecurePass99!",
                "password2": "SecurePass99!",
            },
        )
        self.client.logout()
        logged_in = self.client.login(
            username="alice_student@example.com", password="SecurePass99!"
        )
        self.assertTrue(logged_in)


class ChildDetailStudentCredentialManagementTests(TestCase):
    """Parent can manage existing student credentials from child detail page."""

    def setUp(self):
        self.parent = _make_parent(username="manage_parent")
        self.student = User.objects.create_user(
            username="student_old", password="OldPass123!"
        )
        UserProfile.objects.create(user=self.student, role="student")
        self.child = _make_child(self.parent, first_name="Marya")
        self.child.student_user = self.student
        self.child.save(update_fields=["student_user"])

        self.url = reverse("scheduler:child_detail", kwargs={"child_id": self.child.pk})
        self.client.force_login(self.parent)

    def test_parent_can_update_student_email(self):
        response = self.client.post(
            self.url,
            {
                "update_login_email": "1",
                "new_email": "student_new@example.com",
            },
        )
        self.assertRedirects(response, self.url, fetch_redirect_response=False)

        self.student.refresh_from_db()
        self.assertEqual(self.student.username, "student_new@example.com")
        self.assertEqual(self.student.email, "student_new@example.com")

    def test_duplicate_email_shows_error(self):
        User.objects.create_user(
            username="taken_user@example.com",
            email="taken_user@example.com",
            password="AnyPass123!",
        )

        response = self.client.post(
            self.url,
            {
                "update_login_email": "1",
                "new_email": "taken_user@example.com",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "An account with this email already exists.")

    def test_parent_can_reset_student_password(self):
        response = self.client.post(
            self.url,
            {
                "reset_login_password": "1",
                "new_password1": "BetterPass123!",
                "new_password2": "BetterPass123!",
            },
        )
        self.assertRedirects(response, self.url, fetch_redirect_response=False)

        self.student.refresh_from_db()
        self.assertTrue(self.student.check_password("BetterPass123!"))
        self.assertFalse(self.student.check_password("OldPass123!"))

    def test_child_detail_get_returns_200(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Open Onboarding Flow")

    def test_child_detail_promotes_onboarding_not_legacy_scheduler_steps(self):
        response = self.client.get(self.url)
        onboarding_url = reverse(
            "scheduler:student_onboarding_resume",
            kwargs={"child_id": self.child.pk},
        )
        self.assertContains(response, onboarding_url)
        self.assertNotContains(
            response,
            reverse("scheduler:subject_selection", kwargs={"child_id": self.child.pk}),
        )
        self.assertNotContains(
            response,
            reverse("scheduler:generate_schedule", kwargs={"child_id": self.child.pk}),
        )


class ChildDetailCourseEnrollmentTests(TestCase):
    """Parent can enroll a student into one or more courses from child detail."""

    def setUp(self):
        self.parent = _make_parent(username="course_parent")
        self.child = _make_child(self.parent, first_name="Marya")
        self.client.force_login(self.parent)
        self.url = reverse("scheduler:child_detail", kwargs={"child_id": self.child.pk})

        self.course_math = Course.objects.create(
            parent=self.parent,
            name="Math",
            default_days=[0, 2, 4],
        )
        self.course_science = Course.objects.create(
            parent=self.parent,
            name="Science",
            default_days=[1, 3],
        )

    def test_child_detail_can_enroll_multiple_courses(self):
        response = self.client.post(
            self.url,
            {
                "enroll_courses": "1",
                "course_ids": [str(self.course_math.pk), str(self.course_science.pk)],
            },
        )
        self.assertRedirects(response, self.url, fetch_redirect_response=False)

        enrollments = CourseEnrollment.objects.filter(child=self.child, status="active")
        self.assertEqual(enrollments.count(), 2)
        self.assertTrue(
            enrollments.filter(course=self.course_math, days_of_week=[0, 2, 4]).exists()
        )
        self.assertTrue(
            enrollments.filter(course=self.course_science, days_of_week=[1, 3]).exists()
        )

    def test_child_detail_skips_duplicate_active_enrollment(self):
        CourseEnrollment.objects.create(
            course=self.course_math,
            child=self.child,
            start_date=datetime.date.today(),
            days_of_week=[0, 2, 4],
            status="active",
        )

        self.client.post(
            self.url,
            {
                "enroll_courses": "1",
                "course_ids": [str(self.course_math.pk)],
            },
        )

        self.assertEqual(
            CourseEnrollment.objects.filter(
                child=self.child,
                course=self.course_math,
                status="active",
            ).count(),
            1,
        )


# ---------------------------------------------------------------------------
# S1.5 — Add Child Profile
# ---------------------------------------------------------------------------


def _make_lesson(year="Year 5", subject="Maths", key_stage="KS2"):
    """Helper: create a minimal Lesson to populate the school_year dropdown."""
    import uuid

    return Lesson.objects.create(
        key_stage=key_stage,
        subject_name=subject,
        programme_slug="maths-programme",
        year=year,
        unit_slug="unit-1",
        unit_title="Unit 1",
        lesson_number=1,
        lesson_title="Lesson 1",
        lesson_url=f"https://example.com/lesson/{uuid.uuid4()}",
    )


VALID_CHILD_DATA = {
    "first_name": "Alice",
    "birth_month": 3,
    "birth_year": 2015,
    "school_year": "Year 5",
    "academic_year_start": "2025-09-01",
}


class AddChildAccessTests(TestCase):
    """Gate tests for the retired /children/new/ endpoint."""

    def setUp(self):
        self.parent = _make_parent()
        _make_lesson()  # required to populate school_years dropdown
        self.url = reverse("scheduler:child_new")

    def test_unauthenticated_redirects_to_login(self):
        response = self.client.get(self.url)
        self.assertRedirects(response, f"/accounts/login/?next={self.url}")

    def test_student_role_blocked(self):
        student_user = User.objects.create_user(username="stu", password="Pass123!")
        UserProfile.objects.create(user=student_user, role="student")
        self.client.force_login(student_user)
        response = self.client.get(self.url)
        self.assertRedirects(response, "/", fetch_redirect_response=False)

    def test_parent_can_access_page(self):
        self.client.force_login(self.parent)
        response = self.client.get(self.url, follow=False)
        self.assertRedirects(
            response,
            reverse("scheduler:student_onboarding_new"),
            fetch_redirect_response=False,
        )


class AddChildFormTests(TestCase):
    """Retired legacy endpoint always hands off to onboarding."""

    def setUp(self):
        self.parent = _make_parent()
        _make_lesson()
        self.url = reverse("scheduler:child_new")
        self.client.force_login(self.parent)

    def test_post_redirects_to_onboarding_without_creating_child(self):
        response = self.client.post(self.url, VALID_CHILD_DATA)
        self.assertRedirects(
            response,
            reverse("scheduler:student_onboarding_new"),
            fetch_redirect_response=False,
        )
        self.assertFalse(Child.objects.filter(parent=self.parent).exists())

    def test_missing_first_name_still_redirects_to_onboarding(self):
        data = {**VALID_CHILD_DATA, "first_name": ""}
        response = self.client.post(self.url, data, follow=False)
        self.assertRedirects(
            response,
            reverse("scheduler:student_onboarding_new"),
            fetch_redirect_response=False,
        )

    def test_missing_school_year_still_redirects_to_onboarding(self):
        data = {**VALID_CHILD_DATA, "school_year": ""}
        response = self.client.post(self.url, data, follow=False)
        self.assertRedirects(
            response,
            reverse("scheduler:student_onboarding_new"),
            fetch_redirect_response=False,
        )


class StudentOnboardingFlowTests(TestCase):
    def setUp(self):
        self.parent = _make_parent(username="setup_parent")
        self.client.force_login(self.parent)
        self.new_url = reverse("scheduler:student_onboarding_new")
        for subject_name in ("Maths", "English"):
            lessons = []
            for lesson_number in range(1, 46):
                lessons.append(
                    Lesson(
                        key_stage="ks2",
                        subject_name=subject_name,
                        programme_slug=f"{subject_name.lower()}-prog",
                        year="Year 5",
                        unit_slug=f"{subject_name.lower()}-unit-1",
                        unit_title="Unit 1",
                        lesson_number=lesson_number,
                        lesson_title=f"{subject_name} Lesson {lesson_number}",
                        lesson_url=f"https://example.com/{subject_name.lower()}/{lesson_number}",
                    )
                )
            Lesson.objects.bulk_create(lessons)

    def test_parent_can_access_new_onboarding_route(self):
        response = self.client.get(self.new_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "scheduler/student_onboarding.html")

    def test_onboarding_renders_updated_labels_and_uppercase_key_stage(self):
        child = Child.objects.create(
            parent=self.parent,
            first_name="Nora",
            date_of_birth=datetime.date(2015, 3, 14),
            birth_month=3,
            birth_year=2015,
            school_year="Year 5",
            academic_year_start=datetime.date(2025, 9, 1),
            is_setup_complete=False,
        )
        resume_url = reverse(
            "scheduler:student_onboarding_resume", kwargs={"child_id": child.pk}
        )
        self.client.post(
            resume_url,
            {
                "action": "save_credentials",
                "email": "nora.student@example.com",
                "password1": "SecurePass99!",
                "password2": "SecurePass99!",
            },
        )
        response = self.client.post(
            resume_url,
            {
                "action": "save_school_year",
                "school_year": "Year 5",
            },
            follow=True,
        )
        self.assertContains(response, "Timetable")
        self.assertNotContains(response, "Draft Timetable")
        self.assertContains(response, "KS2")
        self.assertNotContains(response, "Subject colour")

    def test_full_onboarding_flow_creates_subject_courses_slots_and_lessons(self):
        today = timezone.localdate()
        today_weekday = today.weekday()
        next_weekday = (today_weekday + 1) % 7
        response = self.client.post(
            self.new_url,
            {
                "action": "save_info",
                "first_name": "Amina",
                "date_of_birth": "2015-03-14",
            },
        )
        child = Child.objects.get(first_name="Amina")
        self.assertFalse(child.is_setup_complete)
        self.assertRedirects(
            response,
            reverse("scheduler:student_onboarding_resume", kwargs={"child_id": child.pk}),
            fetch_redirect_response=False,
        )
        self.assertEqual(child.birth_month, 3)
        self.assertEqual(child.birth_year, 2015)

        resume_url = reverse("scheduler:student_onboarding_resume", kwargs={"child_id": child.pk})
        self.client.post(
            resume_url,
            {
                "action": "save_credentials",
                "email": "amina.student@example.com",
                "password1": "SecurePass99!",
                "password2": "SecurePass99!",
            },
        )
        child.refresh_from_db()
        self.assertEqual(child.student_user.username, "amina.student@example.com")
        self.assertEqual(child.student_user.email, "amina.student@example.com")

        self.client.post(
            resume_url,
            {
                "action": "save_school_year",
                "school_year": "Year 5",
            },
        )
        child.refresh_from_db()
        self.assertFalse(
            Course.objects.filter(student_owner=child, is_student_workspace=True).exists()
        )

        self.client.post(
            resume_url,
            {
                "action": "save_subjects",
                "subjects": ["Maths", "English"],
                "colour_Maths": "#E63946",
                "colour_English": "#2A9D8F",
            },
        )
        subject_courses = list(
            Course.objects.filter(student_owner=child, is_student_workspace=True).order_by("name")
        )
        self.assertEqual(len(subject_courses), 2)
        maths_course = Course.objects.get(name="Year 5 - Maths", student_owner=child)
        english_course = Course.objects.get(name="Year 5 - English", student_owner=child)
        self.assertTrue(
            CourseSubjectConfig.objects.filter(course=maths_course, subject_name="Maths").exists()
        )
        self.assertTrue(
            EnrolledSubject.objects.filter(child=child, subject_name="English").exists()
        )
        self.assertEqual(maths_course.duration_weeks, 40)
        self.assertEqual(maths_course.frequency_days, 7)
        self.assertEqual(maths_course.grade_years, "5")
        self.assertEqual(list(maths_course.subjects.values_list("name", flat=True)), ["Maths"])
        maths_enrollment = CourseEnrollment.objects.get(
            course=maths_course, child=child, status="active"
        )
        english_enrollment = CourseEnrollment.objects.get(
            course=english_course, child=child, status="active"
        )
        self.assertEqual(maths_enrollment.start_date, today)
        self.assertEqual(english_enrollment.start_date, today)

        self.client.post(
            resume_url,
            {
                "action": "save_timetable",
                "slots_json": json.dumps(
                    [
                        {"subject_name": "Maths", "weekday": today_weekday, "period": 1},
                        {"subject_name": "English", "weekday": next_weekday, "period": 2},
                    ]
                ),
            },
        )
        self.assertEqual(
            CourseSubjectScheduleSlot.objects.filter(
                course_subject__course__student_owner=child,
                course_subject__course__is_student_workspace=True,
            ).count(),
            2,
        )
        maths_cfg = CourseSubjectConfig.objects.get(course=maths_course, subject_name="Maths")
        english_cfg = CourseSubjectConfig.objects.get(course=english_course, subject_name="English")
        self.assertEqual(maths_cfg.lessons_per_week, 1)
        self.assertEqual(maths_cfg.days_of_week, [today_weekday])
        self.assertEqual(english_cfg.lessons_per_week, 1)
        self.assertEqual(english_cfg.days_of_week, [next_weekday])

        response = self.client.post(resume_url, {"action": "generate_lessons"}, follow=True)
        child.refresh_from_db()
        maths_enrollment.refresh_from_db()
        english_enrollment.refresh_from_db()
        self.assertTrue(child.is_setup_complete)
        self.assertEqual(maths_enrollment.start_date, today)
        self.assertEqual(english_enrollment.start_date, today)
        self.assertEqual(
            PlanItem.objects.filter(
                course__student_owner=child,
                course__is_student_workspace=True,
                item_type=PlanItem.ITEM_TYPE_LESSON,
            ).count(),
            80,
        )
        self.assertEqual(
            ScheduledLesson.objects.filter(
                child=child,
                plan_item__course__student_owner=child,
                plan_item__course__is_student_workspace=True,
            ).count(),
            80,
        )
        self.assertEqual(
            ScheduledLesson.objects.filter(
                child=child,
                plan_item__course=maths_course,
                plan_item__day_number=today_weekday + 1,
                plan_item__order=1,
            ).count(),
            40,
        )
        first_maths = ScheduledLesson.objects.get(
            child=child,
            plan_item__course=maths_course,
            plan_item__week_number=1,
            plan_item__day_number=today_weekday + 1,
            plan_item__order=1,
        )
        first_english = ScheduledLesson.objects.get(
            child=child,
            plan_item__course=english_course,
            plan_item__week_number=1,
            plan_item__day_number=next_weekday + 1,
            plan_item__order=2,
        )
        self.assertEqual(first_maths.scheduled_date, today)
        self.assertEqual(
            first_english.scheduled_date,
            today + datetime.timedelta(days=1),
        )
        self.assertEqual(first_maths.order_on_day, 1)
        self.assertEqual(first_english.order_on_day, 2)
        self.assertContains(response, "Lesson cards generated and added to the runtime calendar.")
        self.assertEqual(maths_enrollment.days_of_week, [today_weekday])
        self.assertEqual(english_enrollment.days_of_week, [next_weekday])

    def test_generation_repairs_legacy_workspace_start_date_before_creating_lessons(self):
        child = Child.objects.create(
            parent=self.parent,
            first_name="Repair",
            date_of_birth=datetime.date(2015, 3, 14),
            birth_month=3,
            birth_year=2015,
            school_year="Year 5",
            academic_year_start=datetime.date(2025, 9, 1),
            is_setup_complete=False,
        )
        resume_url = reverse(
            "scheduler:student_onboarding_resume", kwargs={"child_id": child.pk}
        )
        self.client.post(
            resume_url,
            {
                "action": "save_credentials",
                "email": "repair.student@example.com",
                "password1": "SecurePass99!",
                "password2": "SecurePass99!",
            },
        )
        self.client.post(
            resume_url,
            {
                "action": "save_school_year",
                "school_year": "Year 5",
            },
        )
        self.client.post(
            resume_url,
            {
                "action": "save_subjects",
                "subjects": ["Maths"],
                "colour_Maths": "#E63946",
            },
        )
        workspace = Course.objects.get(
            student_owner=child,
            is_student_workspace=True,
            name="Year 5 - Maths",
        )
        enrollment = CourseEnrollment.objects.get(course=workspace, child=child, status="active")
        enrollment.start_date = child.academic_year_start
        enrollment.save(update_fields=["start_date"])
        start_weekday = enrollment.enrolled_at.date().weekday()
        self.client.post(
            resume_url,
            {
                "action": "save_timetable",
                "slots_json": json.dumps(
                    [
                        {"subject_name": "Maths", "weekday": start_weekday, "period": 2},
                    ]
                ),
            },
        )
        self.client.post(resume_url, {"action": "generate_lessons"})
        enrollment.refresh_from_db()
        first_scheduled = ScheduledLesson.objects.filter(
            child=child,
            plan_item__course=workspace,
        ).order_by("scheduled_date", "order_on_day").first()
        self.assertIsNotNone(first_scheduled)
        self.assertEqual(enrollment.start_date, enrollment.enrolled_at.date())
        self.assertEqual(first_scheduled.scheduled_date, enrollment.start_date)
        self.assertEqual(first_scheduled.order_on_day, 2)

    def test_timetable_rejects_rows_outside_one_to_eight(self):
        child = Child.objects.create(
            parent=self.parent,
            first_name="Rows",
            date_of_birth=datetime.date(2015, 3, 14),
            birth_month=3,
            birth_year=2015,
            school_year="Year 5",
            academic_year_start=datetime.date(2025, 9, 1),
            is_setup_complete=False,
        )
        resume_url = reverse(
            "scheduler:student_onboarding_resume", kwargs={"child_id": child.pk}
        )
        self.client.post(
            resume_url,
            {
                "action": "save_credentials",
                "email": "rows.student@example.com",
                "password1": "SecurePass99!",
                "password2": "SecurePass99!",
            },
        )
        self.client.post(
            resume_url,
            {
                "action": "save_school_year",
                "school_year": "Year 5",
            },
        )
        self.client.post(
            resume_url,
            {
                "action": "save_subjects",
                "subjects": ["Maths"],
                "colour_Maths": "#E63946",
            },
        )
        response = self.client.post(
            resume_url,
            {
                "action": "save_timetable",
                "slots_json": json.dumps(
                    [
                        {"subject_name": "Maths", "weekday": 0, "period": 0},
                    ]
                ),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Timetable slots must stay within Mon-Sun and rows 1-8.")


class ChildListTests(TestCase):
    """Tests for the child list page."""

    def setUp(self):
        self.parent = _make_parent()
        _make_lesson()
        self.url = reverse("scheduler:child_list")

    def test_unauthenticated_redirects_to_login(self):
        response = self.client.get(self.url)
        self.assertRedirects(response, f"/accounts/login/?next={self.url}")

    def test_parent_sees_only_their_children(self):
        other_parent = _make_parent(username="parent2")
        child_mine = _make_child(self.parent, "Alice")
        _make_child(other_parent, "Bob")
        self.client.force_login(self.parent)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alice")
        self.assertNotContains(response, "Bob")

    def test_empty_state_shows_add_prompt(self):
        self.client.force_login(self.parent)
        response = self.client.get(self.url)
        self.assertContains(response, "Add your first student")


# ---------------------------------------------------------------------------
# S1.6 — Subject Selection Page
# ---------------------------------------------------------------------------


def _make_lessons_for_child(child, subjects=None):
    """Helper: create Lesson rows for the child's school_year."""
    if subjects is None:
        subjects = [("KS2", "Maths"), ("KS2", "English")]
    lessons = []
    for ks, subj in subjects:
        for i in range(1, 4):  # 3 lessons each
            lessons.append(
                Lesson(
                    key_stage=ks,
                    subject_name=subj,
                    programme_slug=f"{subj.lower()}-prog",
                    year=child.school_year,
                    unit_slug=f"{subj.lower()}-unit-1",
                    unit_title="Unit 1",
                    lesson_number=i,
                    lesson_title=f"Lesson {i}",
                    lesson_url=f"https://example.com/{subj.lower()}/{i}",
                )
            )
    Lesson.objects.bulk_create(lessons)


class SubjectSelectionAccessTests(TestCase):
    """Gate tests for /children/<id>/subjects/."""

    def setUp(self):
        self.parent = _make_parent()
        _make_lesson()
        self.child = _make_child(self.parent)
        self.url = reverse(
            "scheduler:subject_selection", kwargs={"child_id": self.child.pk}
        )

    def test_unauthenticated_redirects_to_login(self):
        response = self.client.get(self.url)
        self.assertRedirects(response, f"/accounts/login/?next={self.url}")

    def test_student_role_blocked(self):
        stu = User.objects.create_user(username="stu2", password="Pass123!")
        UserProfile.objects.create(user=stu, role="student")
        self.client.force_login(stu)
        response = self.client.get(self.url)
        self.assertRedirects(response, "/", fetch_redirect_response=False)

    def test_other_parent_gets_403(self):
        other = _make_parent(username="parent3")
        self.client.force_login(other)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_owner_parent_can_access(self):
        _make_lessons_for_child(self.child)
        self.client.force_login(self.parent)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "scheduler/subject_selection.html")


class SubjectSelectionGetTests(TestCase):
    """Test the GET rendering of the subject selection page."""

    def setUp(self):
        self.parent = _make_parent()
        self.child = _make_child(self.parent)
        _make_lessons_for_child(
            self.child, [("KS2", "Maths"), ("KS2", "English"), ("KS3", "Science")]
        )
        self.url = reverse(
            "scheduler:subject_selection", kwargs={"child_id": self.child.pk}
        )
        self.client.force_login(self.parent)

    def test_subjects_appear_on_page(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Maths")
        self.assertContains(response, "English")
        self.assertContains(response, "Science")

    def test_lesson_count_badge_shown(self):
        response = self.client.get(self.url)
        self.assertContains(response, "3 lessons")

    def test_grouped_context_has_correct_keys(self):
        response = self.client.get(self.url)
        subjects = response.context["subjects"]
        key_stages = {s["is_custom"] for s in subjects}  # sanity check context exists
        subject_names = [s["subject_name"] for s in subjects]
        self.assertIn("Maths", subject_names)
        self.assertIn("Science", subject_names)


class SubjectSelectionPostTests(TestCase):
    """Test POST submission handling."""

    def setUp(self):
        self.parent = _make_parent()
        self.child = _make_child(self.parent)
        _make_lessons_for_child(self.child, [("KS2", "Maths"), ("KS2", "English")])
        self.url = reverse(
            "scheduler:subject_selection", kwargs={"child_id": self.child.pk}
        )
        self.client.force_login(self.parent)

    def test_no_subjects_selected_shows_error(self):
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please select at least one subject")

    def test_valid_post_creates_enrolled_subjects(self):
        self.client.post(
            self.url,
            {
                "subjects": ["Maths", "English"],
            },
        )
        self.assertEqual(EnrolledSubject.objects.filter(child=self.child).count(), 2)

    def test_lessons_per_week_defaults_to_3(self):
        # Step 1 no longer accepts lpw — it always defaults to 3 (set on page 2)
        self.client.post(
            self.url,
            {
                "subjects": ["Maths"],
            },
        )
        es = EnrolledSubject.objects.get(child=self.child, subject_name="Maths")
        self.assertEqual(es.lessons_per_week, 3)

    def test_colour_hex_assigned_from_palette(self):
        from scheduler.views import SUBJECT_COLOUR_PALETTE

        # Post in alphabetical order (English before Maths) to match the
        # palette index order produced by _build_subject_groups.
        self.client.post(
            self.url,
            {
                "subjects": ["English", "Maths"],
            },
        )
        colours = list(
            EnrolledSubject.objects.filter(child=self.child)
            .order_by("id")
            .values_list("colour_hex", flat=True)
        )
        self.assertEqual(colours[0], SUBJECT_COLOUR_PALETTE[0])
        self.assertEqual(colours[1], SUBJECT_COLOUR_PALETTE[1])

    def test_colours_are_distinct_across_subjects(self):
        from scheduler.views import SUBJECT_COLOUR_PALETTE

        self.client.post(
            self.url,
            {
                "subjects": ["Maths", "English"],
            },
        )
        colours = list(
            EnrolledSubject.objects.filter(child=self.child).values_list(
                "colour_hex", flat=True
            )
        )
        self.assertEqual(len(colours), len(set(colours)))

    def test_valid_post_redirects_to_generate(self):
        response = self.client.post(
            self.url,
            {
                "subjects": ["Maths"],
            },
        )
        self.assertRedirects(
            response,
            f"/children/{self.child.pk}/subjects/days/",
            fetch_redirect_response=False,
        )

    def test_resubmission_replaces_previous_enrolments(self):
        # First submission
        self.client.post(self.url, {"subjects": ["Maths"]})
        self.assertEqual(EnrolledSubject.objects.filter(child=self.child).count(), 1)
        # Re-submit with a different selection
        self.client.post(
            self.url,
            {
                "subjects": ["Maths", "English"],
            },
        )
        self.assertEqual(EnrolledSubject.objects.filter(child=self.child).count(), 2)


class GenerateScheduleTests(TestCase):
    """Tests for the generate_schedule() scheduling service (S1.7)."""

    def setUp(self):
        self.parent = _make_parent(username="sched_parent")
        self.child = _make_child(self.parent, first_name="Bob")
        # academic_year_start is 2025-09-01 (Monday)
        # Create 10 Maths lessons across 2 units for Year 5
        for unit, unit_title in [("algebra", "Algebra"), ("fractions", "Fractions")]:
            for n in range(1, 6):
                Lesson.objects.create(
                    key_stage="KS2",
                    subject_name="Maths",
                    programme_slug="maths-year-5",
                    year="Year 5",
                    unit_slug=unit,
                    unit_title=unit_title,
                    lesson_number=n,
                    lesson_title=f"{unit_title} Lesson {n}",
                    lesson_url=f"https://classroom.thenational.academy/{unit}/{n}",
                )
        self.subject = EnrolledSubject.objects.create(
            child=self.child,
            subject_name="Maths",
            key_stage="KS2",
            lessons_per_week=2,
            colour_hex="#E63946",
        )

    def _run(self, subjects=None):
        from scheduler.services import generate_schedule

        if subjects is None:
            subjects = [self.subject]
        return generate_schedule(self.child, subjects)

    def test_returns_integer_count(self):
        count = self._run()
        self.assertIsInstance(count, int)
        self.assertGreater(count, 0)

    def test_schedule_generates_correct_count(self):
        count = self._run()
        self.assertEqual(
            ScheduledLesson.objects.filter(child=self.child).count(), count
        )

    def test_no_weekend_lessons(self):
        self._run()
        for sl in ScheduledLesson.objects.filter(child=self.child):
            self.assertLess(
                sl.scheduled_date.weekday(),
                5,
                f"{sl.scheduled_date} falls on a weekend",
            )

    def test_respects_weekly_pace(self):
        self._run()
        from collections import defaultdict

        week_subject_counts = defaultdict(int)
        for sl in ScheduledLesson.objects.filter(child=self.child).select_related(
            "enrolled_subject"
        ):
            iso_cal = sl.scheduled_date.isocalendar()
            key = (iso_cal[0], iso_cal[1], sl.enrolled_subject_id)
            week_subject_counts[key] += 1
        for count in week_subject_counts.values():
            self.assertLessEqual(count, self.subject.lessons_per_week)

    def test_lessons_in_curriculum_order(self):
        self._run()
        first_sl = (
            ScheduledLesson.objects.filter(child=self.child)
            .select_related("lesson")
            .order_by("scheduled_date", "order_on_day")
            .first()
        )
        self.assertIsNotNone(first_sl)
        self.assertEqual(first_sl.lesson.unit_slug, "algebra")
        self.assertEqual(first_sl.lesson.lesson_number, 1)

    def test_total_does_not_exceed_available_lessons(self):
        count = self._run()
        # Only 10 Maths lessons exist so at most 10 can be scheduled
        self.assertLessEqual(count, 10)

    def test_empty_enrolled_subjects_returns_zero(self):
        count = self._run(subjects=[])
        self.assertEqual(count, 0)


class GenerateScheduleViewTests(TestCase):
    """Tests for generate_schedule_view (S1.8)."""

    GENERATE_URL = "scheduler:generate_schedule"

    def setUp(self):
        self.parent = _make_parent(username="gen_parent")
        self.child = _make_child(self.parent, first_name="Grace")
        # Create 3 curriculum lessons so generate_schedule() has something to work with
        for n in range(1, 4):
            Lesson.objects.create(
                key_stage="KS2",
                subject_name="Maths",
                programme_slug="maths-year-5",
                year="Year 5",
                unit_slug="algebra",
                unit_title="Algebra",
                lesson_number=n,
                lesson_title=f"Maths Lesson {n}",
                lesson_url=f"https://classroom.thenational.academy/algebra/{n}",
            )
        self.enrolled = EnrolledSubject.objects.create(
            child=self.child,
            subject_name="Maths",
            key_stage="KS2",
            lessons_per_week=1,
            colour_hex="#E63946",
        )
        self.url = reverse(self.GENERATE_URL, kwargs={"child_id": self.child.pk})

    # ---------- access ----------

    def test_unauthenticated_redirects_to_login(self):
        response = self.client.get(self.url)
        self.assertRedirects(response, f"/accounts/login/?next={self.url}")

    def test_student_role_blocked(self):
        student = User.objects.create_user(username="stu_gen", password="Pass123!")
        UserProfile.objects.create(user=student, role="student")
        self.client.force_login(student)
        response = self.client.get(self.url)
        self.assertRedirects(response, "/", fetch_redirect_response=False)

    def test_other_parent_gets_403(self):
        other = _make_parent(username="other_gen")
        self.client.force_login(other)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    # ---------- GET ----------

    def test_get_returns_200(self):
        self.client.force_login(self.parent)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_get_shows_child_name(self):
        self.client.force_login(self.parent)
        response = self.client.get(self.url)
        self.assertContains(response, "Grace")

    def test_get_shows_enrolled_subject(self):
        self.client.force_login(self.parent)
        response = self.client.get(self.url)
        self.assertContains(response, "Maths")

    def test_get_context_has_subject_summaries(self):
        self.client.force_login(self.parent)
        response = self.client.get(self.url)
        self.assertIn("subject_summaries", response.context)
        self.assertEqual(len(response.context["subject_summaries"]), 1)

    # ---------- POST ----------

    def test_post_creates_scheduled_lessons(self):
        self.client.force_login(self.parent)
        self.client.post(self.url)
        self.assertGreater(ScheduledLesson.objects.filter(child=self.child).count(), 0)

    def test_post_redirects(self):
        self.client.force_login(self.parent)
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 302)

    def test_post_success_message_contains_name_and_count(self):
        self.client.force_login(self.parent)
        response = self.client.post(self.url, follow=True)
        msgs = list(response.context["messages"])
        self.assertEqual(len(msgs), 1)
        self.assertIn("Grace's schedule is ready", str(msgs[0]))
        self.assertIn("lessons scheduled across 200 days (40 weeks)", str(msgs[0]))

    def test_regenerate_replaces_old_schedule(self):
        self.client.force_login(self.parent)
        self.client.post(self.url)
        count_first = ScheduledLesson.objects.filter(child=self.child).count()
        self.client.post(self.url)
        count_second = ScheduledLesson.objects.filter(child=self.child).count()
        self.assertEqual(count_first, count_second)


class ImportedSubjectSchedulingTests(TestCase):
    def setUp(self):
        self.parent = _make_parent(username="import_parent")
        self.child = _make_child(self.parent, first_name="Ivy")
        self.client.force_login(self.parent)

        for n in range(1, 4):
            Lesson.objects.create(
                key_stage="KS2",
                subject_name="Maths",
                programme_slug="maths-year-6",
                year="Year 6",
                unit_slug="number",
                unit_title="Number",
                lesson_number=n,
                lesson_title=f"Number Lesson {n}",
                lesson_url=f"https://example.com/imported/{n}",
                is_custom=False,
            )

        self.imported_subject = EnrolledSubject.objects.create(
            child=self.child,
            subject_name="Maths (from Year 6)",
            source_subject_name="Maths",
            source_year="Year 6",
            key_stage="Custom",
            lessons_per_week=2,
            colour_hex="#3A86FF",
            days_of_week=[0, 1, 2, 3, 4],
        )

    def test_generate_schedule_uses_canonical_source_subject_name(self):
        from scheduler.services import generate_schedule

        count = generate_schedule(self.child, [self.imported_subject])
        self.assertGreater(count, 0)
        self.assertTrue(
            ScheduledLesson.objects.filter(
                child=self.child,
                lesson__subject_name="Maths",
                enrolled_subject=self.imported_subject,
            ).exists()
        )

    def test_schedule_days_stats_use_source_mapping(self):
        url = reverse("scheduler:schedule_days", kwargs={"child_id": self.child.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        row = response.context["subject_rows"][0]
        self.assertEqual(row["query_subject"], "Maths")
        self.assertEqual(row["query_year"], "Year 6")
        self.assertEqual(row["total_lessons"], 3)

    def test_generate_summary_stats_use_source_mapping(self):
        url = reverse("scheduler:generate_schedule", kwargs={"child_id": self.child.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        summary = response.context["subject_summaries"][0]
        self.assertEqual(summary["query_subject"], "Maths")
        self.assertEqual(summary["query_year"], "Year 6")
        self.assertEqual(summary["total_lessons"], 3)


class PlanningLedSubjectFlowTests(TestCase):
    def setUp(self):
        self.parent = _make_parent(username="planning_flow_parent")
        self.child = _make_child(self.parent, first_name="Mia")
        self.client.force_login(self.parent)

        self.course = Course.objects.create(
            parent=self.parent,
            name="Planning Course",
            duration_weeks=12,
            frequency_days=5,
            default_days=[0, 1, 2, 3, 4],
        )
        self.enrollment = CourseEnrollment.objects.create(
            course=self.course,
            child=self.child,
            start_date=datetime.date(2025, 9, 1),
            days_of_week=[0, 1, 2, 3, 4],
            status="active",
        )

        for lesson_number in range(1, 3):
            Lesson.objects.create(
                key_stage="KS2",
                subject_name="Maths",
                programme_slug="maths-year-5",
                year=self.child.school_year,
                unit_slug="number",
                unit_title="Number",
                lesson_number=lesson_number,
                lesson_title=f"Maths {lesson_number}",
                lesson_url=f"https://example.com/maths/{lesson_number}",
                is_custom=False,
            )

    def test_subject_selection_syncs_course_subject_config(self):
        response = self.client.post(
            reverse("scheduler:subject_selection", kwargs={"child_id": self.child.pk}),
            {"subjects": ["Maths"]},
        )

        self.assertRedirects(
            response,
            reverse("scheduler:schedule_days", kwargs={"child_id": self.child.pk}),
            fetch_redirect_response=False,
        )
        self.assertTrue(
            CourseSubjectConfig.objects.filter(
                course=self.course,
                subject_name="Maths",
                is_active=True,
            ).exists()
        )

    def test_schedule_days_redirects_into_planning_wizard_and_syncs_days(self):
        enrolled_subject = EnrolledSubject.objects.create(
            child=self.child,
            subject_name="Maths",
            key_stage="KS2",
            lessons_per_week=3,
            colour_hex="#E63946",
            days_of_week=[0, 1, 2, 3, 4],
        )

        response = self.client.post(
            reverse("scheduler:schedule_days", kwargs={"child_id": self.child.pk}),
            {
                f"lpw_{enrolled_subject.pk}": "2",
                f"days_{enrolled_subject.pk}": ["0", "2"],
            },
        )

        self.assertRedirects(
            response,
            reverse("planning:oak_wizard", kwargs={"course_id": self.course.pk}),
            fetch_redirect_response=False,
        )
        config = CourseSubjectConfig.objects.get(
            course=self.course, subject_name="Maths"
        )
        self.assertEqual(config.lessons_per_week, 2)
        self.assertEqual(config.days_of_week, [0, 2])


class GenerateScheduleConfirmationGuardTests(TestCase):
    def setUp(self):
        self.parent = _make_parent(username="guard_parent")
        self.child = _make_child(self.parent, first_name="Lina")
        self.client.force_login(self.parent)

        for n in range(1, 3):
            Lesson.objects.create(
                key_stage="KS2",
                subject_name="Maths",
                programme_slug="maths-year-5",
                year="Year 5",
                unit_slug="algebra",
                unit_title="Algebra",
                lesson_number=n,
                lesson_title=f"Algebra {n}",
                lesson_url=f"https://example.com/guard/{n}",
                is_custom=False,
            )

        self.enrolled = EnrolledSubject.objects.create(
            child=self.child,
            subject_name="Maths",
            key_stage="KS2",
            lessons_per_week=1,
            colour_hex="#E63946",
        )

        existing = ScheduledLesson.objects.create(
            child=self.child,
            lesson=Lesson.objects.filter(subject_name="Maths", year="Year 5").first(),
            enrolled_subject=self.enrolled,
            scheduled_date=datetime.date(2025, 9, 1),
            order_on_day=0,
        )
        LessonLog.objects.create(scheduled_lesson=existing, status="complete")

        self.url = reverse(
            "scheduler:generate_schedule", kwargs={"child_id": self.child.pk}
        )

    def test_post_requires_confirmation_when_tracked_history_exists(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Confirm replacement before regenerating",
        )
        self.assertEqual(ScheduledLesson.objects.filter(child=self.child).count(), 1)

    def test_post_with_confirmation_replaces_schedule(self):
        response = self.client.post(self.url, {"confirm_replace_tracked": "1"})
        self.assertEqual(response.status_code, 302)
        self.assertGreater(ScheduledLesson.objects.filter(child=self.child).count(), 0)


class ParentDashboardTests(TestCase):
    """Tests for child_list_view (was parent_dashboard_view, S1.9)."""

    URL = "scheduler:child_list"

    def setUp(self):
        self.parent = _make_parent(username="dash_parent")
        self.child = _make_child(self.parent, first_name="Zara")
        self.url = reverse(self.URL)

    # ---------- access ----------

    def test_unauthenticated_redirects_to_login(self):
        response = self.client.get(self.url)
        self.assertRedirects(response, f"/accounts/login/?next={self.url}")

    def test_student_role_blocked(self):
        student = User.objects.create_user(username="stu_dash", password="Pass123!")
        UserProfile.objects.create(user=student, role="student")
        self.client.force_login(student)
        response = self.client.get(self.url)
        self.assertRedirects(response, "/", fetch_redirect_response=False)

    # ---------- GET with children ----------

    def test_get_returns_200(self):
        self.client.force_login(self.parent)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_child_name_appears_on_page(self):
        self.client.force_login(self.parent)
        response = self.client.get(self.url)
        self.assertContains(response, "Zara")

    def test_primary_student_link_targets_onboarding_resume(self):
        self.client.force_login(self.parent)
        response = self.client.get(self.url)
        onboarding_url = reverse(
            "scheduler:student_onboarding_resume",
            kwargs={"child_id": self.child.pk},
        )
        legacy_url = reverse(
            "scheduler:child_detail",
            kwargs={"child_id": self.child.pk},
        )
        self.assertContains(response, onboarding_url)
        self.assertNotContains(
            response,
            f"onclick=\"window.location='{legacy_url}'\"",
            html=False,
        )

    def test_dashboard_actions_do_not_expose_retired_scheduler_steps(self):
        self.client.force_login(self.parent)
        response = self.client.get(self.url)
        self.assertNotContains(
            response,
            reverse("scheduler:subject_selection", kwargs={"child_id": self.child.pk}),
        )
        self.assertNotContains(
            response,
            reverse("scheduler:generate_schedule", kwargs={"child_id": self.child.pk}),
        )
        self.assertNotContains(
            response,
            reverse("scheduler:create_student_login", kwargs={"child_id": self.child.pk}),
        )
        self.assertContains(
            response,
            reverse("scheduler:child_detail", kwargs={"child_id": self.child.pk}),
        )

    def test_context_has_summaries(self):
        self.client.force_login(self.parent)
        response = self.client.get(self.url)
        self.assertIn("summaries", response.context)
        self.assertEqual(len(response.context["summaries"]), 1)

    def test_summary_has_expected_keys(self):
        self.client.force_login(self.parent)
        response = self.client.get(self.url)
        summary = response.context["summaries"][0]
        for key in (
            "child",
            "total_scheduled",
            "total_complete",
            "completed_this_week",
            "pct_complete",
        ):
            self.assertIn(key, summary)

    def test_zero_scheduled_shows_zero_stats(self):
        self.client.force_login(self.parent)
        response = self.client.get(self.url)
        summary = response.context["summaries"][0]
        self.assertEqual(summary["total_scheduled"], 0)
        self.assertEqual(summary["total_complete"], 0)
        self.assertEqual(summary["pct_complete"], 0)

    def test_parent_sees_only_own_children(self):
        other_parent = _make_parent(username="other_dash")
        _make_child(other_parent, first_name="OtherKid")
        self.client.force_login(self.parent)
        response = self.client.get(self.url)
        self.assertEqual(len(response.context["summaries"]), 1)

    # ---------- GET empty state ----------

    def test_empty_state_shown_when_no_children(self):
        parent2 = _make_parent(username="empty_dash")
        self.client.force_login(parent2)
        response = self.client.get(self.url)
        self.assertEqual(len(response.context["summaries"]), 0)
        self.assertContains(response, "Add your first student")

    # ---------- root redirect ----------

    def test_root_redirects_parent_to_dashboard(self):
        self.client.force_login(self.parent)
        response = self.client.get("/")
        self.assertRedirects(response, reverse("tracker:home_assignments"))

    def test_root_shows_home_for_unauthenticated(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "home.html")
