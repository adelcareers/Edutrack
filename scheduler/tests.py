"""Tests for the scheduler app — S1.4, S1.5 & S1.6."""

import datetime

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from accounts.models import UserProfile
from courses.models import Course, CourseEnrollment
from curriculum.models import Lesson
from scheduler.models import Child, EnrolledSubject, ScheduledLesson


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
                "username": "alice_student",
                "password1": "SecurePass99!",
                "password2": "SecurePass99!",
            },
        )
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        student_user = User.objects.get(username="alice_student")
        self.assertEqual(student_user.profile.role, "student")

    def test_valid_post_links_child_student_user(self):
        self.client.post(
            self.url,
            {
                "username": "alice_student",
                "password1": "SecurePass99!",
                "password2": "SecurePass99!",
            },
        )
        self.child.refresh_from_db()
        self.assertIsNotNone(self.child.student_user)
        self.assertEqual(self.child.student_user.username, "alice_student")

    def test_duplicate_username_shows_error(self):
        User.objects.create_user(username="taken", password="Pass123!")
        response = self.client.post(
            self.url,
            {
                "username": "taken",
                "password1": "SecurePass99!",
                "password2": "SecurePass99!",
            },
        )
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertTrue(form.errors)
        self.assertIn("username", form.errors)

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
                "username": "alice_student",
                "password1": "SecurePass99!",
                "password2": "SecurePass99!",
            },
        )
        self.client.logout()
        logged_in = self.client.login(
            username="alice_student", password="SecurePass99!"
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

    def test_parent_can_update_student_username(self):
        response = self.client.post(
            self.url,
            {
                "update_login_username": "1",
                "new_username": "student_new",
            },
        )
        self.assertRedirects(response, self.url, fetch_redirect_response=False)

        self.student.refresh_from_db()
        self.assertEqual(self.student.username, "student_new")

    def test_duplicate_username_shows_error(self):
        User.objects.create_user(username="taken_user", password="AnyPass123!")

        response = self.client.post(
            self.url,
            {
                "update_login_username": "1",
                "new_username": "taken_user",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This username is already taken.")

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
            default_days="0,2,4",
        )
        self.course_science = Course.objects.create(
            parent=self.parent,
            name="Science",
            default_days="1,3",
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
            enrollments.filter(course=self.course_math, days_of_week="0,2,4").exists()
        )
        self.assertTrue(
            enrollments.filter(course=self.course_science, days_of_week="1,3").exists()
        )

    def test_child_detail_skips_duplicate_active_enrollment(self):
        CourseEnrollment.objects.create(
            course=self.course_math,
            child=self.child,
            start_date=datetime.date.today(),
            days_of_week="0,2,4",
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
    """Gate tests: who can reach /children/new/."""

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
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "scheduler/child_new.html")


class AddChildFormTests(TestCase):
    """Form submission and validation tests."""

    def setUp(self):
        self.parent = _make_parent()
        _make_lesson()
        self.url = reverse("scheduler:child_new")
        self.client.force_login(self.parent)

    def test_valid_post_creates_child_linked_to_parent(self):
        self.client.post(self.url, VALID_CHILD_DATA)
        child = Child.objects.get(first_name="Alice")
        self.assertEqual(child.parent, self.parent)

    def test_valid_post_redirects_to_subject_selection(self):
        response = self.client.post(self.url, VALID_CHILD_DATA)
        child = Child.objects.get(first_name="Alice")
        self.assertRedirects(
            response,
            f"/children/{child.pk}/",
            fetch_redirect_response=False,
        )

    def test_missing_first_name_shows_error(self):
        data = {**VALID_CHILD_DATA, "first_name": ""}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("first_name", response.context["errors"])

    def test_missing_school_year_shows_error(self):
        data = {**VALID_CHILD_DATA, "school_year": ""}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("school_year", response.context["errors"])

    def test_school_year_choices_populated_from_lesson_table(self):
        _make_lesson(year="Year 6")
        response = self.client.get(self.url)
        school_years = response.context["school_years"]
        self.assertIn("Year 5", school_years)
        self.assertIn("Year 6", school_years)


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
        self.assertIn("lessons scheduled across 180 days", str(msgs[0]))

    def test_regenerate_replaces_old_schedule(self):
        self.client.force_login(self.parent)
        self.client.post(self.url)
        count_first = ScheduledLesson.objects.filter(child=self.child).count()
        self.client.post(self.url)
        count_second = ScheduledLesson.objects.filter(child=self.child).count()
        self.assertEqual(count_first, count_second)


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
