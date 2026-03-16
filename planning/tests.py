import datetime

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from accounts.models import UserProfile
from courses.models import Course, GlobalAssignmentType
from planning.models import AssignmentPlanItem, CourseAssignmentTemplate, StudentAssignment
from scheduler.models import Child


class StudentAssignmentSelectionTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username='plan-parent', password='pw')
        UserProfile.objects.create(user=self.parent, role='parent')
        self.client.login(username='plan-parent', password='pw')

        self.course = Course.objects.create(
            parent=self.parent,
            name='Math',
            duration_weeks=12,
            frequency_days=5,
        )
        self.global_type = GlobalAssignmentType.objects.create(
            parent=self.parent,
            name='Homework',
            color='#9ca3af',
            order=0,
        )

        self.child_one = Child.objects.create(
            parent=self.parent,
            first_name='Ali',
            birth_month=1,
            birth_year=2013,
            school_year='Year 8',
            academic_year_start=datetime.date(2025, 9, 1),
        )
        self.child_two = Child.objects.create(
            parent=self.parent,
            first_name='Noor',
            birth_month=2,
            birth_year=2014,
            school_year='Year 7',
            academic_year_start=datetime.date(2025, 9, 1),
        )

        self.enrollment_one = self.course.enrollments.create(
            child=self.child_one,
            start_date=datetime.date(2026, 1, 6),
            days_of_week='0,2,4',
            status='active',
        )
        self.enrollment_two = self.course.enrollments.create(
            child=self.child_two,
            start_date=datetime.date(2026, 1, 6),
            days_of_week='0,2,4',
            status='active',
        )

    def test_create_assignment_only_for_selected_students(self):
        response = self.client.get(reverse('planning:plan_course', args=[self.course.pk]))
        self.assertEqual(response.status_code, 200)

        assignment_type_id = response.context['assignment_types'].first().pk

        post_data = {
            'assignment_name': 'Worksheet 1',
            'assignment_type': str(assignment_type_id),
            'week_number': '1',
            'day_number': '1',
            'due_in_days': '0',
            'description': '',
            'teacher_notes': '',
            'assign_enrollment_selection_present': '1',
            'assign_enrollment_ids': [str(self.enrollment_one.pk)],
        }

        response = self.client.post(
            reverse('planning:plan_course', args=[self.course.pk]),
            data=post_data,
        )
        self.assertEqual(response.status_code, 302)

        self.assertEqual(StudentAssignment.objects.count(), 1)
        student_assignment = StudentAssignment.objects.get()
        self.assertEqual(student_assignment.enrollment_id, self.enrollment_one.pk)

    def test_edit_assignment_can_remove_student_assignment(self):
        response = self.client.get(reverse('planning:plan_course', args=[self.course.pk]))
        self.assertEqual(response.status_code, 200)
        assignment_type = response.context['assignment_types'].first()

        template = CourseAssignmentTemplate.objects.create(
            course=self.course,
            assignment_type=assignment_type,
            name='Quiz 1',
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

        StudentAssignment.objects.create(
            enrollment=self.enrollment_one,
            plan_item=plan_item,
            due_date=datetime.date(2026, 1, 6),
            status='pending',
        )
        second_assignment = StudentAssignment.objects.create(
            enrollment=self.enrollment_two,
            plan_item=plan_item,
            due_date=datetime.date(2026, 1, 6),
            status='pending',
        )

        post_data = {
            'plan_item_id': str(plan_item.pk),
            'assignment_name': 'Quiz 1',
            'assignment_type': str(assignment_type.pk),
            'week_number': '1',
            'day_number': '1',
            'due_in_days': '0',
            'description': '',
            'teacher_notes': '',
            'assign_enrollment_selection_present': '1',
            'assign_enrollment_ids': [str(self.enrollment_one.pk)],
            f'student_status_{second_assignment.pk}': 'pending',
        }

        response = self.client.post(
            reverse('planning:plan_course', args=[self.course.pk]),
            data=post_data,
        )
        self.assertEqual(response.status_code, 302)

        self.assertTrue(
            StudentAssignment.objects.filter(
                plan_item=plan_item,
                enrollment=self.enrollment_one,
            ).exists()
        )
        self.assertFalse(
            StudentAssignment.objects.filter(
                plan_item=plan_item,
                enrollment=self.enrollment_two,
            ).exists()
        )

    def test_edit_assignment_can_add_student_assignment(self):
        response = self.client.get(reverse('planning:plan_course', args=[self.course.pk]))
        self.assertEqual(response.status_code, 200)
        assignment_type = response.context['assignment_types'].first()

        template = CourseAssignmentTemplate.objects.create(
            course=self.course,
            assignment_type=assignment_type,
            name='Essay 1',
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

        StudentAssignment.objects.create(
            enrollment=self.enrollment_one,
            plan_item=plan_item,
            due_date=datetime.date(2026, 1, 6),
            status='pending',
        )

        post_data = {
            'plan_item_id': str(plan_item.pk),
            'assignment_name': 'Essay 1',
            'assignment_type': str(assignment_type.pk),
            'week_number': '1',
            'day_number': '1',
            'due_in_days': '0',
            'description': '',
            'teacher_notes': '',
            'assign_enrollment_selection_present': '1',
            'assign_enrollment_ids': [
                str(self.enrollment_one.pk),
                str(self.enrollment_two.pk),
            ],
        }

        response = self.client.post(
            reverse('planning:plan_course', args=[self.course.pk]),
            data=post_data,
        )
        self.assertEqual(response.status_code, 302)

        self.assertTrue(
            StudentAssignment.objects.filter(
                plan_item=plan_item,
                enrollment=self.enrollment_two,
            ).exists()
        )
