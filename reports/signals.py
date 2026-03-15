from django.db.models.signals import post_save
from django.dispatch import receiver

from courses.models import AssignmentType, Course, CourseEnrollment
from planning.models import StudentAssignment
from reports.services_gradebook import recalculate_course_grades, recalculate_enrollment_grade


@receiver(post_save, sender=StudentAssignment)
def update_grade_summary_after_assignment_save(sender, instance, **kwargs):
    recalculate_enrollment_grade(instance.enrollment)


@receiver(post_save, sender=AssignmentType)
def update_course_grade_summaries_after_assignment_type_change(sender, instance, **kwargs):
    recalculate_course_grades(instance.course)


@receiver(post_save, sender=Course)
def update_course_grade_summaries_after_course_change(sender, instance, **kwargs):
    update_fields = kwargs.get('update_fields')
    if not update_fields:
        recalculate_course_grades(instance)
        return
    if {'grading_style', 'use_assignment_weights'} & set(update_fields):
        recalculate_course_grades(instance)


@receiver(post_save, sender=CourseEnrollment)
def ensure_enrollment_summary(sender, instance, created, **kwargs):
    if created:
        recalculate_enrollment_grade(instance)
