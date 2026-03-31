from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

from courses.models import CourseEnrollment
from reports.models import (
    EnrollmentGradeSummary,
    GradeScaleProfile,
    default_grade_scale_bands,
)

ZERO = Decimal("0")
HUNDRED = Decimal("100")


def _to_decimal(value, default=ZERO):
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _round2(value):
    return _to_decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def get_effective_points_available(student_assignment):
    """Resolve points available with per-assignment override then type default."""
    if student_assignment.points_available is not None:
        return _to_decimal(student_assignment.points_available)

    plan_item = getattr(student_assignment, "new_plan_item", None)
    detail = getattr(plan_item, "assignment_detail", None) if plan_item else None
    assignment_type = getattr(detail, "assignment_type", None)
    if assignment_type is None:
        legacy_plan_item = getattr(student_assignment, "plan_item", None)
        legacy_template = getattr(legacy_plan_item, "template", None)
        assignment_type = getattr(legacy_template, "assignment_type", None)
    if assignment_type is None:
        return HUNDRED

    if assignment_type.default_points_available is not None:
        return _to_decimal(assignment_type.default_points_available)

    return HUNDRED


def get_assignment_percent(student_assignment):
    """Return the effective percent for one assignment, or 0 for ungraded work."""
    if student_assignment.score_percent is not None:
        pct = _to_decimal(student_assignment.score_percent)
        return max(ZERO, min(HUNDRED, pct))

    if student_assignment.score is not None:
        points_available = get_effective_points_available(student_assignment)
        if points_available > ZERO:
            pct = (_to_decimal(student_assignment.score) / points_available) * HUNDRED
            return max(ZERO, min(HUNDRED, pct))

    # Ungraded assignments count as zero by product decision.
    return ZERO


def get_effective_grade_scale(course):
    """Return per-course grade scale or fallback to parent global default."""
    course_scale = GradeScaleProfile.objects.filter(
        parent=course.parent,
        course=course,
        is_active=True,
    ).first()
    if course_scale:
        return course_scale.bands

    global_scale = GradeScaleProfile.objects.filter(
        parent=course.parent,
        course__isnull=True,
        is_active=True,
    ).first()
    if global_scale:
        return global_scale.bands

    return default_grade_scale_bands()


def map_percent_to_letter_and_gpa(percent, scale_bands):
    """Map final percent to letter grade and GPA from scale bands."""
    value = _to_decimal(percent)
    for band in scale_bands:
        lower = _to_decimal(band.get("min", 0))
        upper = _to_decimal(band.get("max", 100))
        if lower <= value <= upper:
            letter = band.get("letter", "")
            gpa = _to_decimal(band.get("gpa", 0))
            return letter, _round2(gpa)
    return "", None


def recalculate_enrollment_grade(enrollment):
    """Recalculate and persist grade summary for one enrollment."""
    if not CourseEnrollment.objects.filter(pk=enrollment.pk).exists():
        return None

    assignments = list(
        enrollment.assignments.select_related(
            "new_plan_item__assignment_detail__assignment_type",
            "plan_item__template__assignment_type",
        )
    )

    total_count = len(assignments)
    today = timezone.localdate()
    missing_count = 0
    late_count = 0
    graded_count = 0

    by_assignment_type = {}
    for assignment in assignments:
        if assignment.status in {"pending", "overdue"} and assignment.due_date < today:
            missing_count += 1
        if assignment.status == "overdue":
            late_count += 1
        if (
            assignment.status in {"complete", "needs_grading"}
            and assignment.completed_at
        ):
            if assignment.completed_at.date() > assignment.due_date:
                late_count += 1

        percent = get_assignment_percent(assignment)

        if assignment.score is not None or assignment.score_percent is not None:
            graded_count += 1

        plan_item = getattr(assignment, "new_plan_item", None)
        detail = getattr(plan_item, "assignment_detail", None) if plan_item else None
        assignment_type = getattr(detail, "assignment_type", None)
        if assignment_type is None:
            legacy_plan_item = getattr(assignment, "plan_item", None)
            legacy_template = getattr(legacy_plan_item, "template", None)
            assignment_type = getattr(legacy_template, "assignment_type", None)
        if assignment_type is None:
            continue

        bucket = by_assignment_type.setdefault(
            assignment_type.id,
            {
                "name": assignment_type.name,
                "weight": int(assignment_type.weight),
                "percents": [],
            },
        )
        bucket["percents"].append(percent)

    if not assignments:
        final_percent = ZERO
    elif enrollment.course.use_assignment_weights:
        weighted_total = ZERO
        total_weight = ZERO
        for bucket in by_assignment_type.values():
            percents = bucket["percents"]
            if not percents:
                continue
            avg = sum(percents, ZERO) / Decimal(len(percents))
            weight = Decimal(bucket["weight"])
            weighted_total += avg * weight
            total_weight += weight

        if total_weight > ZERO:
            final_percent = weighted_total / total_weight
        else:
            all_percents = [
                pct
                for bucket in by_assignment_type.values()
                for pct in bucket["percents"]
            ]
            final_percent = (sum(all_percents, ZERO) / Decimal(len(all_percents))) if all_percents else ZERO
    else:
        all_percents = [
            pct for bucket in by_assignment_type.values() for pct in bucket["percents"]
        ]
        final_percent = (sum(all_percents, ZERO) / Decimal(len(all_percents))) if all_percents else ZERO

    final_percent = _round2(final_percent)
    letter, gpa = map_percent_to_letter_and_gpa(
        final_percent, get_effective_grade_scale(enrollment.course)
    )

    breakdown = {}
    for bucket in by_assignment_type.values():
        percents = bucket["percents"]
        avg = (sum(percents, ZERO) / Decimal(len(percents))) if percents else ZERO
        breakdown[bucket["name"]] = {
            "weight": bucket["weight"],
            "count": len(percents),
            "average_percent": float(_round2(avg)),
        }

    summary, _ = EnrollmentGradeSummary.objects.get_or_create(enrollment=enrollment)
    summary.final_percent = final_percent
    summary.letter_grade = letter
    summary.gpa_points = gpa
    summary.graded_assignments_count = graded_count
    summary.total_assignments_count = total_count
    summary.missing_assignments_count = missing_count
    summary.late_assignments_count = late_count
    summary.assignment_type_breakdown = breakdown
    summary.save()

    return summary


def recalculate_course_grades(course):
    """Recalculate grade summaries for all enrollments in a course."""
    for enrollment in course.enrollments.all().select_related(
        "course", "child", "course__parent"
    ):
        recalculate_enrollment_grade(enrollment)


def lazy_backfill_enrollment_grade_summary(enrollment):
    """Populate summary if absent, otherwise return existing cached row."""
    summary = EnrollmentGradeSummary.objects.filter(enrollment=enrollment).first()
    if summary:
        return summary
    return recalculate_enrollment_grade(enrollment)
