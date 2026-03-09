"""Tests for the scheduler app — S1.4, S1.5 & S1.6."""

import datetime
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User

from accounts.models import UserProfile
from curriculum.models import Lesson
from scheduler.models import Child, EnrolledSubject


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


# ---------------------------------------------------------------------------
# S1.5 — Add Child Profile
# ---------------------------------------------------------------------------

def _make_lesson(year='Year 5', subject='Maths', key_stage='KS2'):
    """Helper: create a minimal Lesson to populate the school_year dropdown."""
    return Lesson.objects.create(
        key_stage=key_stage,
        subject_name=subject,
        programme_slug='maths-programme',
        year=year,
        unit_slug='unit-1',
        unit_title='Unit 1',
        lesson_number=1,
        lesson_title='Lesson 1',
        lesson_url='https://example.com/lesson/1',
    )


VALID_CHILD_DATA = {
    'first_name': 'Alice',
    'birth_month': 3,
    'birth_year': 2015,
    'school_year': 'Year 5',
    'academic_year_start': '2025-09-01',
}


class AddChildAccessTests(TestCase):
    """Gate tests: who can reach /children/add/."""

    def setUp(self):
        self.parent = _make_parent()
        _make_lesson()  # required for ChildForm.__init__ to build year choices
        self.url = reverse('scheduler:add_child')

    def test_unauthenticated_redirects_to_login(self):
        response = self.client.get(self.url)
        self.assertRedirects(response, f'/accounts/login/?next={self.url}')

    def test_student_role_blocked(self):
        student_user = User.objects.create_user(username='stu', password='Pass123!')
        UserProfile.objects.create(user=student_user, role='student')
        self.client.force_login(student_user)
        response = self.client.get(self.url)
        self.assertRedirects(response, '/')

    def test_parent_can_access_page(self):
        self.client.force_login(self.parent)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'scheduler/add_child.html')


class AddChildFormTests(TestCase):
    """Form submission and validation tests."""

    def setUp(self):
        self.parent = _make_parent()
        _make_lesson()
        self.url = reverse('scheduler:add_child')
        self.client.force_login(self.parent)

    def test_valid_post_creates_child_linked_to_parent(self):
        self.client.post(self.url, VALID_CHILD_DATA)
        child = Child.objects.get(first_name='Alice')
        self.assertEqual(child.parent, self.parent)

    def test_valid_post_redirects_to_subject_selection(self):
        response = self.client.post(self.url, VALID_CHILD_DATA)
        child = Child.objects.get(first_name='Alice')
        self.assertRedirects(
            response,
            f'/children/{child.pk}/subjects/',
            fetch_redirect_response=False,
        )

    def test_missing_first_name_shows_error(self):
        data = {**VALID_CHILD_DATA, 'first_name': ''}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertIn('first_name', response.context['form'].errors)

    def test_missing_school_year_shows_error(self):
        data = {**VALID_CHILD_DATA, 'school_year': ''}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertIn('school_year', response.context['form'].errors)

    def test_school_year_choices_populated_from_lesson_table(self):
        _make_lesson(year='Year 6')
        response = self.client.get(self.url)
        choices = [c[0] for c in response.context['form'].fields['school_year'].choices]
        self.assertIn('Year 5', choices)
        self.assertIn('Year 6', choices)


class ChildListTests(TestCase):
    """Tests for the child list page."""

    def setUp(self):
        self.parent = _make_parent()
        _make_lesson()
        self.url = reverse('scheduler:child_list')

    def test_unauthenticated_redirects_to_login(self):
        response = self.client.get(self.url)
        self.assertRedirects(response, f'/accounts/login/?next={self.url}')

    def test_parent_sees_only_their_children(self):
        other_parent = _make_parent(username='parent2')
        child_mine = _make_child(self.parent, 'Alice')
        _make_child(other_parent, 'Bob')
        self.client.force_login(self.parent)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Alice')
        self.assertNotContains(response, 'Bob')

    def test_empty_state_shows_add_prompt(self):
        self.client.force_login(self.parent)
        response = self.client.get(self.url)
        self.assertContains(response, "Add your first child")


# ---------------------------------------------------------------------------
# S1.6 — Subject Selection Page
# ---------------------------------------------------------------------------

def _make_lessons_for_child(child, subjects=None):
    """Helper: create Lesson rows for the child's school_year."""
    if subjects is None:
        subjects = [('KS2', 'Maths'), ('KS2', 'English')]
    lessons = []
    for ks, subj in subjects:
        for i in range(1, 4):  # 3 lessons each
            lessons.append(Lesson(
                key_stage=ks,
                subject_name=subj,
                programme_slug=f'{subj.lower()}-prog',
                year=child.school_year,
                unit_slug=f'{subj.lower()}-unit-1',
                unit_title='Unit 1',
                lesson_number=i,
                lesson_title=f'Lesson {i}',
                lesson_url=f'https://example.com/{subj.lower()}/{i}',
            ))
    Lesson.objects.bulk_create(lessons)


class SubjectSelectionAccessTests(TestCase):
    """Gate tests for /children/<id>/subjects/."""

    def setUp(self):
        self.parent = _make_parent()
        _make_lesson()
        self.child = _make_child(self.parent)
        self.url = reverse('scheduler:subject_selection', kwargs={'child_id': self.child.pk})

    def test_unauthenticated_redirects_to_login(self):
        response = self.client.get(self.url)
        self.assertRedirects(response, f'/accounts/login/?next={self.url}')

    def test_student_role_blocked(self):
        stu = User.objects.create_user(username='stu2', password='Pass123!')
        UserProfile.objects.create(user=stu, role='student')
        self.client.force_login(stu)
        response = self.client.get(self.url)
        self.assertRedirects(response, '/')

    def test_other_parent_gets_403(self):
        other = _make_parent(username='parent3')
        self.client.force_login(other)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_owner_parent_can_access(self):
        _make_lessons_for_child(self.child)
        self.client.force_login(self.parent)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'scheduler/subject_selection.html')


class SubjectSelectionGetTests(TestCase):
    """Test the GET rendering of the subject selection page."""

    def setUp(self):
        self.parent = _make_parent()
        self.child = _make_child(self.parent)
        _make_lessons_for_child(self.child, [('KS2', 'Maths'), ('KS2', 'English'), ('KS3', 'Science')])
        self.url = reverse('scheduler:subject_selection', kwargs={'child_id': self.child.pk})
        self.client.force_login(self.parent)

    def test_subjects_appear_on_page(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'Maths')
        self.assertContains(response, 'English')
        self.assertContains(response, 'Science')

    def test_lesson_count_badge_shown(self):
        response = self.client.get(self.url)
        self.assertContains(response, '3 lessons')

    def test_grouped_context_has_correct_keys(self):
        response = self.client.get(self.url)
        grouped = response.context['grouped']
        self.assertIn('KS2', grouped)
        self.assertIn('KS3', grouped)


class SubjectSelectionPostTests(TestCase):
    """Test POST submission handling."""

    def setUp(self):
        self.parent = _make_parent()
        self.child = _make_child(self.parent)
        _make_lessons_for_child(self.child, [('KS2', 'Maths'), ('KS2', 'English')])
        self.url = reverse('scheduler:subject_selection', kwargs={'child_id': self.child.pk})
        self.client.force_login(self.parent)

    def test_no_subjects_selected_shows_error(self):
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please select at least one subject")

    def test_valid_post_creates_enrolled_subjects(self):
        self.client.post(self.url, {
            'subjects': ['Maths', 'English'],
            'pace_Maths': '2',
            'pace_English': '1',
        })
        self.assertEqual(EnrolledSubject.objects.filter(child=self.child).count(), 2)

    def test_lessons_per_week_stored_correctly(self):
        self.client.post(self.url, {
            'subjects': ['Maths'],
            'pace_Maths': '3',
        })
        es = EnrolledSubject.objects.get(child=self.child, subject_name='Maths')
        self.assertEqual(es.lessons_per_week, 3)

    def test_colour_hex_assigned_from_palette(self):
        from scheduler.views import SUBJECT_COLOUR_PALETTE
        self.client.post(self.url, {
            'subjects': ['Maths', 'English'],
            'pace_Maths': '1',
            'pace_English': '1',
        })
        colours = list(
            EnrolledSubject.objects.filter(child=self.child)
            .order_by('id')
            .values_list('colour_hex', flat=True)
        )
        self.assertEqual(colours[0], SUBJECT_COLOUR_PALETTE[0])
        self.assertEqual(colours[1], SUBJECT_COLOUR_PALETTE[1])

    def test_colours_are_distinct_across_subjects(self):
        from scheduler.views import SUBJECT_COLOUR_PALETTE
        self.client.post(self.url, {
            'subjects': ['Maths', 'English'],
            'pace_Maths': '1',
            'pace_English': '1',
        })
        colours = list(
            EnrolledSubject.objects.filter(child=self.child)
            .values_list('colour_hex', flat=True)
        )
        self.assertEqual(len(colours), len(set(colours)))

    def test_valid_post_redirects_to_generate(self):
        response = self.client.post(self.url, {
            'subjects': ['Maths'],
            'pace_Maths': '1',
        })
        self.assertRedirects(
            response,
            f'/children/{self.child.pk}/generate/',
            fetch_redirect_response=False,
        )

    def test_resubmission_replaces_previous_enrolments(self):
        # First submission
        self.client.post(self.url, {'subjects': ['Maths'], 'pace_Maths': '1'})
        self.assertEqual(EnrolledSubject.objects.filter(child=self.child).count(), 1)
        # Re-submit with a different selection
        self.client.post(self.url, {
            'subjects': ['Maths', 'English'],
            'pace_Maths': '2',
            'pace_English': '1',
        })
        self.assertEqual(EnrolledSubject.objects.filter(child=self.child).count(), 2)
