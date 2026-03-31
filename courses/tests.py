import datetime

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from accounts.models import UserProfile
from courses.models import (
    AssignmentType,
    Course,
    CourseArchive,
    GlobalAssignmentType,
    sync_course_assignment_types_from_global,
)
from planning.models import (
    ActivityProgress,
    AssignmentPlanItem,
    CourseAssignmentTemplate,
    PlanItem,
    StudentAssignment,
)
from scheduler.models import Child


class CourseHardDeleteArchiveTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="parent1", password="pw")
        UserProfile.objects.create(user=self.parent, role="parent")

        self.other_parent = User.objects.create_user(username="parent2", password="pw")
        UserProfile.objects.create(user=self.other_parent, role="parent")

        self.course = Course.objects.create(
            parent=self.parent,
            name="Biology",
            duration_weeks=12,
            frequency_days=3,
            grading_style="percent_graded",
            use_assignment_weights=True,
        )
        self.assignment_type = AssignmentType.objects.create(
            course=self.course, name="Homework", weight=100, order=0
        )
        self.plan_type = AssignmentType.objects.create(
            course=self.course,
            name="Homework",
            color="#9ca3af",
            order=0,
        )
        self.template = CourseAssignmentTemplate.objects.create(
            course=self.course,
            assignment_type=self.plan_type,
            name="Cell Worksheet",
            description="Chapter 1 worksheet",
            is_graded=True,
            due_offset_days=2,
            order=0,
        )
        self.plan_item = AssignmentPlanItem.objects.create(
            course=self.course,
            template=self.template,
            week_number=1,
            day_number=1,
            due_in_days=2,
            order=0,
            notes="Bring notes",
        )

        self.child = Child.objects.create(
            parent=self.parent,
            first_name="Ali",
            birth_month=4,
            birth_year=2013,
            school_year="Year 8",
            academic_year_start=datetime.date(2025, 9, 1),
        )
        self.enrollment = self.course.enrollments.create(
            child=self.child,
            start_date=datetime.date(2026, 1, 6),
            days_of_week=[0, 2, 4],
            status="active",
        )
        StudentAssignment.objects.create(
            enrollment=self.enrollment,
            plan_item=self.plan_item,
            due_date=datetime.date(2026, 1, 8),
            status="pending",
        )

    def test_hard_delete_creates_archive_and_deletes_course(self):
        self.client.login(username="parent1", password="pw")
        response = self.client.post(
            reverse("courses:course_delete", kwargs={"course_id": self.course.pk})
        )

        self.assertRedirects(response, reverse("courses:course_list"))
        self.assertFalse(Course.objects.filter(pk=self.course.pk).exists())

        archive = CourseArchive.objects.get(parent=self.parent)
        self.assertEqual(archive.course_name, "Biology")
        self.assertEqual(archive.remark, "course deleted")
        self.assertGreaterEqual(len(archive.enrollment_history), 1)
        self.assertGreaterEqual(len(archive.assignment_history), 1)

        first_assignment = archive.assignment_history[0]
        self.assertEqual(first_assignment["template_name"], "Cell Worksheet")
        self.assertEqual(first_assignment["child_name"], "Ali")

    def test_hard_delete_for_other_parent_returns_forbidden(self):
        self.client.login(username="parent2", password="pw")
        response = self.client.post(
            reverse("courses:course_delete", kwargs={"course_id": self.course.pk})
        )
        self.assertEqual(response.status_code, 403)

    def test_archived_records_pages_visible_to_parent(self):
        CourseArchive.objects.create(
            parent=self.parent,
            original_course_id=99,
            course_name="Archived Maths",
            remark="course deleted",
            course_data={"name": "Archived Maths"},
            enrollment_history=[],
            assignment_history=[],
        )

        self.client.login(username="parent1", password="pw")
        list_response = self.client.get(reverse("courses:archived_courses"))
        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, "Archived Maths")

        archive = CourseArchive.objects.get(course_name="Archived Maths")
        detail_response = self.client.get(
            reverse("courses:archived_course_detail", kwargs={"archive_id": archive.pk})
        )
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, "Archived Maths")


class SingleSourceAssignmentTypeSyncTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="sync-parent", password="pw")
        UserProfile.objects.create(user=self.parent, role="parent")
        self.course = Course.objects.create(
            parent=self.parent,
            name="History",
            use_assignment_weights=True,
        )

    def test_sync_creates_and_updates_course_assignment_types_from_global(self):
        hw = GlobalAssignmentType.objects.create(
            parent=self.parent,
            name="Homework",
            color="#9ca3af",
            order=0,
        )
        quiz = GlobalAssignmentType.objects.create(
            parent=self.parent,
            name="Quiz",
            color="#60a5fa",
            order=1,
        )

        sync_course_assignment_types_from_global(self.course)
        rows = list(
            AssignmentType.objects.filter(course=self.course)
            .order_by("order", "name")
            .values_list("global_type_id", "name", "color", "is_hidden")
        )
        self.assertEqual(
            rows,
            [
                (hw.pk, "Homework", "#9ca3af", False),
                (quiz.pk, "Quiz", "#60a5fa", False),
            ],
        )

        hw.name = "Practice"
        hw.color = "#111111"
        hw.is_hidden = True
        hw.order = 2
        hw.save()
        quiz.delete()
        lab = GlobalAssignmentType.objects.create(
            parent=self.parent,
            name="Lab",
            color="#86efac",
            order=0,
        )

        sync_course_assignment_types_from_global(self.course)
        rows = list(
            AssignmentType.objects.filter(course=self.course)
            .order_by("order", "name")
            .values_list("global_type_id", "name", "color", "is_hidden")
        )
        self.assertEqual(
            rows,
            [
                (lab.pk, "Lab", "#86efac", False),
                (hw.pk, "Practice", "#111111", True),
            ],
        )

    def test_sync_preserves_existing_weight_for_matched_rows(self):
        gt = GlobalAssignmentType.objects.create(
            parent=self.parent,
            name="Homework",
            color="#9ca3af",
            order=0,
        )
        AssignmentType.objects.create(
            course=self.course,
            global_type=gt,
            name="Homework",
            color="#9ca3af",
            weight=40,
            order=0,
        )

        sync_course_assignment_types_from_global(self.course)
        at = AssignmentType.objects.get(course=self.course, global_type=gt)
        self.assertEqual(at.weight, 40)


class CourseSubjectConfigDeleteTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="cfg-parent", password="pw")
        UserProfile.objects.create(user=self.parent, role="parent")
        self.client.login(username="cfg-parent", password="pw")

        self.course = Course.objects.create(parent=self.parent, name="Delete Course")
        self.child = Child.objects.create(
            parent=self.parent,
            first_name="Sami",
            birth_month=1,
            birth_year=2014,
            school_year="Year 6",
            academic_year_start=datetime.date(2025, 9, 1),
        )
        self.enrollment = self.course.enrollments.create(
            child=self.child,
            start_date=datetime.date(2026, 1, 6),
            days_of_week=[0, 1, 2, 3, 4],
            status="active",
        )
        self.config = self.course.subject_configs.create(
            subject_name="Science",
            year="Year 6",
            lessons_per_week=1,
            days_of_week=[0],
        )
        self.plan_item = PlanItem.objects.create(
            course=self.course,
            item_type=PlanItem.ITEM_TYPE_ACTIVITY,
            week_number=1,
            day_number=1,
            name="Lab",
        )
        from planning.models import ActivityPlanDetail

        ActivityPlanDetail.objects.create(
            plan_item=self.plan_item, course_subject=self.config
        )
        template = CourseAssignmentTemplate.objects.create(
            course=self.course,
            assignment_type=None,
            item_kind="activity",
            name="Lab",
        )
        legacy = AssignmentPlanItem.objects.create(
            course=self.course,
            template=template,
            week_number=1,
            day_number=1,
        )
        self.progress = ActivityProgress.objects.create(
            enrollment=self.enrollment,
            plan_item=legacy,
            new_plan_item=self.plan_item,
            status="pending",
        )

    def test_subject_config_soft_delete_deactivates_related_plan_items(self):
        response = self.client.post(
            reverse(
                "courses:subject_config_deactivate",
                kwargs={"config_id": self.config.pk},
            )
        )
        self.assertEqual(response.status_code, 302)
        self.config.refresh_from_db()
        self.plan_item.refresh_from_db()
        self.assertFalse(self.config.is_active)
        self.assertFalse(self.plan_item.is_active)

    def test_subject_config_hard_delete_removes_related_plan_items_and_progress(self):
        response = self.client.post(
            reverse(
                "courses:subject_config_delete", kwargs={"config_id": self.config.pk}
            ),
            {"confirm": "DELETE"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(self.course.subject_configs.filter(pk=self.config.pk).exists())
        self.assertFalse(PlanItem.objects.filter(pk=self.plan_item.pk).exists())
        self.assertFalse(ActivityProgress.objects.filter(pk=self.progress.pk).exists())

    def test_sync_preserves_course_hidden_when_global_visible(self):
        gt = GlobalAssignmentType.objects.create(
            parent=self.parent,
            name="Quiz",
            color="#60a5fa",
            order=0,
            is_hidden=False,
        )
        AssignmentType.objects.create(
            course=self.course,
            global_type=gt,
            name="Quiz",
            color="#60a5fa",
            is_hidden=True,
            order=0,
        )

        sync_course_assignment_types_from_global(self.course)
        at = AssignmentType.objects.get(course=self.course, global_type=gt)
        self.assertTrue(at.is_hidden)
