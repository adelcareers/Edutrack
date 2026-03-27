import datetime

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from accounts.models import UserProfile
from courses.models import Course, GlobalAssignmentType
from curriculum.models import Lesson
from planning.models import (
    AssignmentPlanItem,
    CourseAssignmentTemplate,
    StudentAssignment,
)
from scheduler.models import Child, EnrolledSubject, ScheduledLesson


class StudentAssignmentSelectionTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="plan-parent", password="pw")
        UserProfile.objects.create(user=self.parent, role="parent")
        self.client.login(username="plan-parent", password="pw")

        self.course = Course.objects.create(
            parent=self.parent,
            name="Math",
            duration_weeks=12,
            frequency_days=5,
        )
        self.global_type = GlobalAssignmentType.objects.create(
            parent=self.parent,
            name="Homework",
            color="#9ca3af",
            order=0,
        )

        self.child_one = Child.objects.create(
            parent=self.parent,
            first_name="Ali",
            birth_month=1,
            birth_year=2013,
            school_year="Year 8",
            academic_year_start=datetime.date(2025, 9, 1),
        )
        self.child_two = Child.objects.create(
            parent=self.parent,
            first_name="Noor",
            birth_month=2,
            birth_year=2014,
            school_year="Year 7",
            academic_year_start=datetime.date(2025, 9, 1),
        )

        self.enrollment_one = self.course.enrollments.create(
            child=self.child_one,
            start_date=datetime.date(2026, 1, 6),
            days_of_week="0,2,4",
            status="active",
        )
        self.enrollment_two = self.course.enrollments.create(
            child=self.child_two,
            start_date=datetime.date(2026, 1, 6),
            days_of_week="0,2,4",
            status="active",
        )

    def test_create_assignment_only_for_selected_students(self):
        response = self.client.get(
            reverse("planning:plan_course", args=[self.course.pk])
        )
        self.assertEqual(response.status_code, 200)

        assignment_type_id = response.context["assignment_types"].first().pk

        post_data = {
            "assignment_name": "Worksheet 1",
            "assignment_type": str(assignment_type_id),
            "week_number": "1",
            "day_number": "1",
            "due_in_days": "0",
            "description": "",
            "teacher_notes": "",
            "assign_enrollment_selection_present": "1",
            "assign_enrollment_ids": [str(self.enrollment_one.pk)],
        }

        response = self.client.post(
            reverse("planning:plan_course", args=[self.course.pk]),
            data=post_data,
        )
        self.assertEqual(response.status_code, 302)

        self.assertEqual(StudentAssignment.objects.count(), 1)
        student_assignment = StudentAssignment.objects.get()
        self.assertEqual(student_assignment.enrollment_id, self.enrollment_one.pk)

    def test_edit_assignment_can_remove_student_assignment(self):
        response = self.client.get(
            reverse("planning:plan_course", args=[self.course.pk])
        )
        self.assertEqual(response.status_code, 200)
        assignment_type = response.context["assignment_types"].first()

        template = CourseAssignmentTemplate.objects.create(
            course=self.course,
            assignment_type=assignment_type,
            name="Quiz 1",
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
            status="pending",
        )
        second_assignment = StudentAssignment.objects.create(
            enrollment=self.enrollment_two,
            plan_item=plan_item,
            due_date=datetime.date(2026, 1, 6),
            status="pending",
        )

        post_data = {
            "plan_item_id": str(plan_item.pk),
            "assignment_name": "Quiz 1",
            "assignment_type": str(assignment_type.pk),
            "week_number": "1",
            "day_number": "1",
            "due_in_days": "0",
            "description": "",
            "teacher_notes": "",
            "assign_enrollment_selection_present": "1",
            "assign_enrollment_ids": [str(self.enrollment_one.pk)],
            f"student_status_{second_assignment.pk}": "pending",
        }

        response = self.client.post(
            reverse("planning:plan_course", args=[self.course.pk]),
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
        response = self.client.get(
            reverse("planning:plan_course", args=[self.course.pk])
        )
        self.assertEqual(response.status_code, 200)
        assignment_type = response.context["assignment_types"].first()

        template = CourseAssignmentTemplate.objects.create(
            course=self.course,
            assignment_type=assignment_type,
            name="Essay 1",
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
            status="pending",
        )

        post_data = {
            "plan_item_id": str(plan_item.pk),
            "assignment_name": "Essay 1",
            "assignment_type": str(assignment_type.pk),
            "week_number": "1",
            "day_number": "1",
            "due_in_days": "0",
            "description": "",
            "teacher_notes": "",
            "assign_enrollment_selection_present": "1",
            "assign_enrollment_ids": [
                str(self.enrollment_one.pk),
                str(self.enrollment_two.pk),
            ],
        }

        response = self.client.post(
            reverse("planning:plan_course", args=[self.course.pk]),
            data=post_data,
        )
        self.assertEqual(response.status_code, 302)

        self.assertTrue(
            StudentAssignment.objects.filter(
                plan_item=plan_item,
                enrollment=self.enrollment_two,
            ).exists()
        )

    def test_hidden_assignment_type_not_shown_in_planning_form(self):
        response = self.client.get(
            reverse("planning:plan_course", args=[self.course.pk])
        )
        self.assertEqual(response.status_code, 200)

        assignment_type = response.context["assignment_types"].first()
        assignment_type.is_hidden = True
        assignment_type.save(update_fields=["is_hidden"])

        response = self.client.get(
            reverse("planning:plan_course", args=[self.course.pk])
        )
        self.assertEqual(response.status_code, 200)
        assignment_type_ids = list(
            response.context["assignment_types"].values_list("id", flat=True)
        )
        self.assertNotIn(assignment_type.id, assignment_type_ids)

    def test_create_activity_item_does_not_require_assignment_type(self):
        response = self.client.post(
            reverse("planning:plan_course", args=[self.course.pk]),
            data={
                "item_kind": "activity",
                "assignment_name": "Read together",
                "week_number": "2",
                "day_number": "3",
                "due_in_days": "0",
                "description": "Read a chapter and discuss.",
                "teacher_notes": "Keep it relaxed.",
                "assign_enrollment_selection_present": "1",
            },
        )
        self.assertEqual(response.status_code, 302)

        plan_item = AssignmentPlanItem.objects.get()
        self.assertEqual(plan_item.template.item_kind, "activity")
        self.assertIsNone(plan_item.template.assignment_type)

    def test_create_activity_item_does_not_create_student_assignments(self):
        response = self.client.post(
            reverse("planning:plan_course", args=[self.course.pk]),
            data={
                "item_kind": "activity",
                "assignment_name": "Outdoor activity",
                "week_number": "3",
                "day_number": "1",
                "due_in_days": "0",
                "description": "Nature walk.",
                "teacher_notes": "Bring notebook.",
                "assign_enrollment_selection_present": "1",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(StudentAssignment.objects.count(), 0)

    def test_create_lesson_item_creates_scheduled_lesson(self):
        enrolled_subject = EnrolledSubject.objects.create(
            child=self.child_one,
            subject_name="Maths",
            key_stage="KS3",
            lessons_per_week=3,
            colour_hex="#3A86FF",
            days_of_week="0,1,2,3,4",
        )
        Lesson.objects.create(
            key_stage="KS3",
            subject_name="Maths",
            programme_slug="maths-year-8",
            year=self.child_one.school_year,
            unit_slug="algebra",
            unit_title="Algebra",
            lesson_number=1,
            lesson_title="Intro Algebra",
            lesson_url="https://example.com/oak/intro-algebra",
            is_custom=False,
        )

        response = self.client.post(
            reverse("planning:plan_course", args=[self.course.pk]),
            data={
                "item_kind": "lesson",
                "assignment_name": "Maths Lesson",
                "week_number": "1",
                "day_number": "2",
                "due_in_days": "0",
                "description": "Lesson planning item",
                "teacher_notes": "Auto-scheduled from OAK.",
                "lesson_child_id": str(self.child_one.pk),
                "lesson_subject_id": str(enrolled_subject.pk),
            },
        )

        self.assertEqual(response.status_code, 302)
        plan_item = AssignmentPlanItem.objects.get()
        self.assertEqual(plan_item.template.item_kind, "lesson")
        self.assertEqual(plan_item.lesson_child_id, self.child_one.pk)
        self.assertEqual(plan_item.lesson_enrolled_subject_id, enrolled_subject.pk)
        self.assertIsNotNone(plan_item.scheduled_lesson_id)
        self.assertEqual(ScheduledLesson.objects.count(), 1)


class PlanningTeacherAccessTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(username="plan-teacher", password="pw")
        UserProfile.objects.create(user=self.teacher, role="teacher")
        self.client.login(username="plan-teacher", password="pw")

        self.course = Course.objects.create(
            parent=self.teacher,
            name="Teacher Course",
            duration_weeks=12,
            frequency_days=5,
        )

    def test_teacher_can_access_plan_sessions(self):
        response = self.client.get(reverse("planning:plan_sessions"))
        self.assertEqual(response.status_code, 200)

    def test_teacher_can_access_plan_course(self):
        response = self.client.get(reverse("planning:plan_course", args=[self.course.pk]))
        self.assertEqual(response.status_code, 200)
