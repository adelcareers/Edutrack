import logging

from django.contrib import messages
from django.db.models import Count
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from accounts.decorators import role_required_any
from courses.models import Course
from curriculum.models import Lesson
from scheduler.services import generate_schedule

from .context_builders import (
    ITEM_KIND_TO_WORKFLOW,
    WORKFLOW_ASSIGNMENTS,
    WORKFLOW_TO_ITEM_KIND,
    build_plan_course_context,
    build_plan_url,
    course_days,
    course_weeks,
    normalize_scope,
    normalize_workflow,
    safe_int,
)
from .models import AssignmentPlanItem
from django.db import models
from .services import (
    create_plan_item_from_post,
    delete_plan_item_legacy,
    update_plan_item_from_post,
)
from . import services as planning_services
from planning.models import PlanItem as NewPlanItemModel
from courses.models import CourseSubjectConfig
from planning.models import StudentAssignment, ActivityProgress
from scheduler.models import ScheduledLesson
from .services import create_subject_configs_from_selection, generate_plan_grid

logger = logging.getLogger(__name__)


@role_required_any("parent", "teacher")
def initiate_oak_scheduling_view(request, course_id):
    try:
        course = get_object_or_404(Course, pk=course_id, parent=request.user)
        active_enrollments = list(
            course.enrollments.select_related("child").filter(status="active")
        )
        children = {enrollment.child for enrollment in active_enrollments}
        scheduled_count = 0
        for child in children:
            child_enrollments = [
                enr for enr in active_enrollments if enr.child_id == child.id
            ]
            scheduled_count += generate_schedule(child, child_enrollments)
        messages.success(
            request,
            f"OAK lesson scheduling complete. {scheduled_count} lessons scheduled.",
        )
        return HttpResponseRedirect(reverse("planning:plan_course", args=[course_id]))
    except Exception as e:
        logger.exception(
            "Error during OAK lesson scheduling for course_id=%s", course_id
        )
        messages.error(
            request,
            f"An error occurred during OAK lesson scheduling: {str(e)}. "
            "Please contact support.",
        )
        return HttpResponseRedirect(reverse("planning:plan_course", args=[course_id]))


@role_required_any("parent", "teacher")
def plan_sessions_view(request):
    courses = list(
        Course.objects.filter(parent=request.user, is_archived=False).order_by("name")
    )
    cards = []
    for course in courses:
        week_rows = [
            {
                "week": week,
                "days": list(range(1, max(course.frequency_days, 1) + 1)),
            }
            for week in range(1, max(course.duration_weeks, 1) + 1)
        ]
        cards.append(
            {
                "course": course,
                "week_rows": week_rows,
                "days_per_week": course.frequency_days,
                "weeks_count": course.duration_weeks,
            }
        )
    return render(request, "planning/sessions.html", {"cards": cards})


@role_required_any("parent", "teacher")
def plan_course_view(request, course_id):
    course = get_object_or_404(Course, pk=course_id, parent=request.user)
    weeks = course_weeks(course)
    days = course_days(course)

    selected_week = safe_int(request.GET.get("week", 1), 1) if weeks else 1
    selected_day = safe_int(request.GET.get("day", 1), 1) if days else 1
    if selected_week not in weeks:
        selected_week = weeks[0] if weeks else 1
    if selected_day not in days:
        selected_day = days[0] if days else 1

    workflow = normalize_workflow(request.GET.get("workflow", WORKFLOW_ASSIGNMENTS))
    scope = normalize_scope(request.GET.get("scope", "day"))

    active_enrollments = list(
        course.enrollments.select_related("child").filter(status="active")
    )

    # ── DELETE handler ──────────────────────────────────────────────
    if request.method == "POST" and request.POST.get("delete_id"):
        delete_id = safe_int(request.POST.get("delete_id"), None)
        post_workflow = normalize_workflow(request.POST.get("workflow", workflow))
        post_scope = normalize_scope(request.POST.get("scope", scope))
        week_number = safe_int(
            request.POST.get("week_number", selected_week), selected_week
        )
        day_number = safe_int(
            request.POST.get("day_number", selected_day), selected_day
        )
        if delete_id:
            plan_item = get_object_or_404(
                AssignmentPlanItem, pk=delete_id, course=course
            )
            delete_plan_item_legacy(plan_item)
        return redirect(
            build_plan_url(request.path, week_number, day_number, post_workflow, post_scope)
        )

    # ── CREATE / UPDATE handler ─────────────────────────────────────
    if request.method == "POST":
        post_workflow = normalize_workflow(request.POST.get("workflow", workflow))
        post_scope = normalize_scope(request.POST.get("scope", scope))
        plan_item_id = safe_int(request.POST.get("plan_item_id"), None)

        item_kind = (
            request.POST.get("item_kind", WORKFLOW_TO_ITEM_KIND[post_workflow])
            .strip()
            .lower()
        )
        if item_kind not in ITEM_KIND_TO_WORKFLOW:
            item_kind = WORKFLOW_TO_ITEM_KIND[post_workflow]
        post_workflow = ITEM_KIND_TO_WORKFLOW[item_kind]

        week_number = safe_int(
            request.POST.get("week_number", selected_week), selected_week
        )
        day_number = safe_int(
            request.POST.get("day_number", selected_day), selected_day
        )
        if week_number not in weeks:
            week_number = selected_week
        if day_number not in days:
            day_number = selected_day

        template_name = request.POST.get("assignment_name", "").strip()

        if plan_item_id:
            plan_item = get_object_or_404(
                AssignmentPlanItem, pk=plan_item_id, course=course
            )
            plan_item, error = update_plan_item_from_post(
                plan_item, course, request.POST, request.FILES, active_enrollments
            )
            # Attempt to update corresponding new PlanItem if present
            try:
                # try to locate an associated new PlanItem via the scheduled_lesson bridge
                new_plan = None
                if getattr(plan_item, "scheduled_lesson", None):
                    sl = plan_item.scheduled_lesson
                    if sl and sl.plan_item_id:
                        new_plan = NewPlanItemModel.objects.filter(pk=sl.plan_item_id).first()
                # fallback: try to find by course + grid position + name
                if new_plan is None:
                    new_plan = NewPlanItemModel.objects.filter(
                        course=course,
                        week_number=plan_item.week_number,
                        day_number=plan_item.day_number,
                        name=plan_item.template.name,
                    ).first()
                if new_plan:
                    # map fields from legacy template/plan_item to new detail fields
                    detail_fields = {}
                    tk = (plan_item.template.item_kind or "assignment").lower()
                    if tk == "assignment":
                        detail_fields["assignment_type"] = plan_item.template.assignment_type
                        detail_fields["is_graded"] = plan_item.template.is_graded
                        detail_fields["due_offset_days"] = plan_item.template.due_offset_days
                    elif tk == "lesson":
                        # try to map enrolled subject -> course_subject
                        cs = None
                        if plan_item.lesson_enrolled_subject:
                            source = (plan_item.lesson_enrolled_subject.source_subject_name or "").strip()
                            name = (plan_item.lesson_enrolled_subject.subject_name or "").strip()
                            cs = CourseSubjectConfig.objects.filter(course=course).filter(
                                models.Q(subject_name__iexact=name) | models.Q(source_subject_name__iexact=source)
                            ).first()
                        if cs is None:
                            new_plan = None
                        else:
                            detail_fields["course_subject"] = cs
                            detail_fields["curriculum_lesson"] = getattr(plan_item.scheduled_lesson, "lesson", None)
                    # update the new plan item
                    if new_plan is not None:
                        planning_services.update_plan_item(new_plan, **{
                            "week_number": plan_item.week_number,
                            "day_number": plan_item.day_number,
                            "name": plan_item.template.name,
                            "description": plan_item.template.description,
                            **detail_fields,
                        })
            except Exception:
                logger.exception("Dual-write update to PlanItem failed for legacy id=%s", plan_item_id)
        else:
            plan_item, error = create_plan_item_from_post(
                course, request.POST, request.FILES, active_enrollments
            )
            # Dual-write: create a new PlanItem to mirror legacy creation
            try:
                if plan_item is not None:
                    tk = (plan_item.template.item_kind or "assignment").lower()
                    item_type = {
                        "assignment": NewPlanItemModel.ITEM_TYPE_ASSIGNMENT,
                        "lesson": NewPlanItemModel.ITEM_TYPE_LESSON,
                        "activity": NewPlanItemModel.ITEM_TYPE_ACTIVITY,
                    }.get(tk, NewPlanItemModel.ITEM_TYPE_ASSIGNMENT)

                    detail_kwargs = {}
                    if item_type == NewPlanItemModel.ITEM_TYPE_ASSIGNMENT:
                        detail_kwargs["assignment_type"] = plan_item.template.assignment_type
                        detail_kwargs["is_graded"] = plan_item.template.is_graded
                        detail_kwargs["due_offset_days"] = plan_item.template.due_offset_days
                    elif item_type == NewPlanItemModel.ITEM_TYPE_LESSON:
                        cs = None
                        if plan_item.lesson_enrolled_subject:
                            source = (plan_item.lesson_enrolled_subject.source_subject_name or "").strip()
                            name = (plan_item.lesson_enrolled_subject.subject_name or "").strip()
                            cs = CourseSubjectConfig.objects.filter(course=course).filter(
                                models.Q(subject_name__iexact=name) | models.Q(source_subject_name__iexact=source)
                            ).first()
                        if cs is None:
                            new_plan = None
                        else:
                            detail_kwargs["course_subject"] = cs
                            detail_kwargs["curriculum_lesson"] = getattr(plan_item.scheduled_lesson, "lesson", None)

                    if item_type != NewPlanItemModel.ITEM_TYPE_LESSON or cs is not None:
                        new_plan = planning_services.create_plan_item(
                            course=course,
                            item_type=item_type,
                            week_number=plan_item.week_number,
                            day_number=plan_item.day_number,
                            name=plan_item.template.name,
                            description=plan_item.template.description,
                            order=plan_item.order,
                            is_active=True,
                            **detail_kwargs,
                        )
                    else:
                        new_plan = None

                    # Backfill bridge FKs: student assignments and activity progress
                    if new_plan is not None:
                        try:
                            StudentAssignment.objects.filter(plan_item=plan_item).update(new_plan_item=new_plan)
                        except Exception:
                            logger.exception("Failed to backfill StudentAssignment.new_plan_item for legacy id=%s", plan_item.id)
                        try:
                            ActivityProgress.objects.filter(plan_item=plan_item).update(new_plan_item=new_plan)
                        except Exception:
                            logger.exception("Failed to backfill ActivityProgress.new_plan_item for legacy id=%s", plan_item.id)
                        # If scheduled_lesson exists, link it
                        if getattr(plan_item, "scheduled_lesson", None):
                            try:
                                sl = plan_item.scheduled_lesson
                                sl.plan_item = new_plan
                                if getattr(new_plan, "lesson_detail", None):
                                    sl.course_subject = new_plan.lesson_detail.course_subject
                                sl.save(update_fields=["plan_item", "course_subject"])
                            except Exception:
                                logger.exception("Failed to link ScheduledLesson to new PlanItem for legacy id=%s", plan_item.id)
            except Exception:
                logger.exception("Dual-write create PlanItem failed for legacy id=%s", getattr(plan_item, "id", None))

        if error:
            messages.error(request, error)
            return redirect(
                build_plan_url(
                    request.path, week_number, day_number,
                    post_workflow, post_scope, create=True,
                )
            )

        if plan_item_id and template_name:
            return redirect(
                build_plan_url(
                    request.path, week_number, day_number,
                    post_workflow, post_scope, create=True, edit_id=plan_item_id,
                )
            )
        if template_name and plan_item is not None:
            return redirect(
                build_plan_url(
                    request.path, week_number, day_number,
                    post_workflow, post_scope, create=True, edit_id=plan_item.id,
                )
            )
        return redirect(
            build_plan_url(request.path, week_number, day_number, post_workflow, post_scope)
        )

    # ── GET handler ─────────────────────────────────────────────────
    context = build_plan_course_context(course, request.GET, active_enrollments)
    return render(request, "planning/detail.html", context)


@role_required_any("parent", "teacher")
def oak_wizard_view(request, course_id):
    """Multi-step wizard to configure and generate an Oak-based lesson plan grid.

    Step 1 (GET or POST with step=1): Select subjects + year from curriculum.
    Step 2 (POST with step=2): Configure lessons_per_week and days_of_week per subject.
    Step 3 (POST with step=3): Generate the plan grid and redirect to plan_course.
    """
    course = get_object_or_404(Course, pk=course_id, parent=request.user)

    # Fetch all distinct (subject_name, year) pairs from Oak curriculum
    available_subjects = (
        Lesson.objects.filter(is_custom=False)
        .values("subject_name", "year")
        .annotate(lesson_count=Count("id"))
        .order_by("subject_name", "year")
    )

    step = request.POST.get("step", "1") if request.method == "POST" else "1"

    if request.method == "POST" and step == "2":
        # Process subject selections, render configuration form
        selected = []
        for key in request.POST:
            if key.startswith("subject_"):
                # key format: subject_{subject_name}__{year}
                parts = key[len("subject_"):].split("__", 1)
                if len(parts) == 2:
                    subject_name, year = parts
                    selected.append({"subject_name": subject_name, "year": year})

        if not selected:
            messages.error(request, "Please select at least one subject.")
            return render(
                request,
                "planning/oak_wizard.html",
                {"course": course, "step": 1, "available_subjects": available_subjects},
            )

        return render(
            request,
            "planning/oak_wizard.html",
            {
                "course": course,
                "step": 2,
                "selected_subjects": selected,
                "available_subjects": available_subjects,
                "day_choices": [
                    (0, "Mon"), (1, "Tue"), (2, "Wed"), (3, "Thu"),
                    (4, "Fri"), (5, "Sat"), (6, "Sun"),
                ],
            },
        )

    if request.method == "POST" and step == "3":
        # Process configuration and generate the plan grid
        subject_configs_data = []
        idx = 0
        while True:
            subject_name = request.POST.get(f"subject_name_{idx}")
            if subject_name is None:
                break
            year = request.POST.get(f"year_{idx}", "")
            try:
                lessons_per_week = int(request.POST.get(f"lessons_per_week_{idx}", 3))
            except (TypeError, ValueError):
                lessons_per_week = 3
            valid_days = set(range(max(course.frequency_days, 1)))
            days_of_week = sorted(
                {
                    int(d)
                    for d in request.POST.getlist(f"days_of_week_{idx}")
                    if str(d).isdigit() and int(d) in valid_days
                }
            )
            if not days_of_week:
                messages.error(
                    request,
                    f"{subject_name} must be assigned to at least one of the course's available days.",
                )
                return redirect(reverse("planning:oak_wizard", args=[course_id]))
            colour_hex = request.POST.get(f"colour_hex_{idx}", "#6c757d")
            if lessons_per_week < 1 or lessons_per_week > 10:
                messages.error(
                    request,
                    f"{subject_name} must have between 1 and 10 lessons per week.",
                )
                return redirect(reverse("planning:oak_wizard", args=[course_id]))
            subject_configs_data.append({
                "subject_name": subject_name,
                "year": year,
                "lessons_per_week": lessons_per_week,
                "days_of_week": days_of_week,
                "colour_hex": colour_hex,
                "source": "oak",
                "source_subject_name": subject_name,
                "source_year": year,
            })
            idx += 1

        if not subject_configs_data:
            messages.error(request, "No subjects configured.")
            return redirect(reverse("planning:oak_wizard", args=[course_id]))

        try:
            configs = create_subject_configs_from_selection(course, subject_configs_data)
            created_count = generate_plan_grid(course, configs)
            messages.success(
                request,
                f"Oak lesson plan generated: {created_count} lesson slots added to the planning grid.",
            )
        except Exception:
            logger.exception("Oak wizard grid generation failed for course_id=%s", course_id)
            messages.error(request, "An error occurred while generating the plan grid.")

        return redirect(reverse("planning:plan_course", args=[course_id]))

    # Step 1: GET — show subject selection form
    return render(
        request,
        "planning/oak_wizard.html",
        {
            "course": course,
            "step": 1,
            "available_subjects": available_subjects,
        },
    )
