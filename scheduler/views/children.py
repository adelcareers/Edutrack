"""Child management views."""

import datetime

from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from accounts.decorators import role_required
from accounts.forms import StudentCreationForm
from accounts.models import UserProfile
from courses.models import Course, CourseEnrollment
from curriculum.models import Lesson
from scheduler.models import Child


@role_required("parent")
def child_list_view(request):
    """Display all active children for the parent."""
    today = datetime.date.today()
    week_start = today - datetime.timedelta(days=today.weekday())
    week_end = week_start + datetime.timedelta(days=6)

    children = Child.objects.filter(parent=request.user, is_active=True)

    # Build per-child progress summaries
    summaries = []
    for child in children:
        total_scheduled = child.scheduled_lessons.count()
        total_complete = child.scheduled_lessons.filter(log__status="complete").count()
        completed_this_week = child.scheduled_lessons.filter(
            scheduled_date__gte=week_start,
            scheduled_date__lte=week_end,
            log__status="complete",
        ).count()
        pct_complete = (
            round(total_complete / total_scheduled * 100) if total_scheduled else 0
        )
        summaries.append(
            {
                "child": child,
                "total_scheduled": total_scheduled,
                "total_complete": total_complete,
                "completed_this_week": completed_this_week,
                "pct_complete": pct_complete,
            }
        )

    return render(
        request,
        "scheduler/child_list.html",
        {
            "summaries": summaries,
        },
    )


@role_required("parent")
def child_new_view(request):
    """Inline new-student form — same layout as child_detail but for creation."""
    raw_years = Lesson.objects.values_list("year", flat=True).distinct()
    school_years = sorted(
        set(raw_years),
        key=lambda y: int(y.split()[-1]) if y.split()[-1].isdigit() else 99,
    )

    errors = {}
    form_data = {}

    if request.method == "POST":
        first_name = request.POST.get("first_name", "").strip()
        school_year = request.POST.get("school_year", "").strip()
        form_data = {"first_name": first_name, "school_year": school_year}

        if not first_name:
            errors["first_name"] = "Student name is required."
        if not school_year:
            errors["school_year"] = "School year is required."

        if not errors:
            today = datetime.date.today()
            academic_start = (
                datetime.date(today.year, 9, 1)
                if today.month >= 9
                else datetime.date(today.year - 1, 9, 1)
            )
            child = Child(
                parent=request.user,
                first_name=first_name,
                school_year=school_year,
                birth_month=today.month,
                birth_year=today.year - 10,
                academic_year_start=academic_start,
            )
            if request.FILES.get("photo"):
                child.photo = request.FILES["photo"]
            child.save()

            # Auto-create a course named after the school year and enrol child
            course, _ = Course.objects.get_or_create(
                parent=request.user,
                name=school_year,
                defaults={
                    "color": "#6c757d",
                    "duration_weeks": 36,
                    "frequency_days": 5,
                    "default_days": [0, 1, 2, 3, 4],
                },
            )
            CourseEnrollment.objects.get_or_create(
                course=course,
                child=child,
                defaults={
                    "start_date": today,
                    "days_of_week": [0, 1, 2, 3, 4],
                    "status": "active",
                },
            )

            messages.success(
                request,
                f"{child.first_name} added! Use the Oak Wizard to schedule lessons.",
            )
            return redirect(reverse("planning:oak_wizard", args=[course.pk]))

    return render(
        request,
        "scheduler/child_new.html",
        {
            "school_years": school_years,
            "errors": errors,
            "form_data": form_data,
        },
    )


@role_required("parent")
def delete_child_view(request, child_id):
    """Delete a child after the parent confirms by typing the child's name."""
    child = get_object_or_404(Child, pk=child_id, parent=request.user)

    if request.method == "POST":
        confirm_name = request.POST.get("confirm_name", "").strip()
        if confirm_name == child.first_name:
            child_name = child.first_name
            child.delete()
            messages.success(request, f"{child_name} has been deleted.")
        else:
            messages.error(request, "Name did not match. Student not deleted.")

    return redirect("scheduler:child_list")


@role_required("parent")
def child_detail_view(request, child_id):
    """Student detail page: edit info, create login, view enrolled courses."""
    child = get_object_or_404(Child, pk=child_id, parent=request.user)

    raw_years = Lesson.objects.values_list("year", flat=True).distinct()
    school_years = sorted(
        set(raw_years),
        key=lambda y: int(y.split()[-1]) if y.split()[-1].isdigit() else 99,
    )

    info_errors = {}
    login_form = StudentCreationForm()
    login_manage_errors = {}
    login_manage_data = {}
    login_section_open = child.student_user is None

    if request.method == "POST":
        if "save_student" in request.POST:
            first_name = request.POST.get("first_name", "").strip()
            school_year = request.POST.get("school_year", "").strip()
            if not first_name:
                info_errors["first_name"] = "Student name is required."
            if not school_year:
                info_errors["school_year"] = "School year is required."
            if not info_errors:
                child.first_name = first_name
                child.school_year = school_year
                if request.FILES.get("photo"):
                    child.photo = request.FILES["photo"]
                child.save()
                messages.success(request, f"{child.first_name} updated successfully.")
                return redirect("scheduler:child_detail", child_id=child.pk)

        elif "create_login" in request.POST:
            if child.student_user is not None:
                messages.info(
                    request, f"{child.first_name} already has login credentials."
                )
                return redirect("scheduler:child_detail", child_id=child.pk)
            login_form = StudentCreationForm(request.POST)
            login_section_open = True
            if login_form.is_valid():
                username = login_form.cleaned_data["username"]
                password = login_form.cleaned_data["password1"]
                student_user = User.objects.create_user(
                    username=username, password=password
                )
                UserProfile.objects.create(user=student_user, role="student")
                child.student_user = student_user
                child.save()
                messages.success(request, f"Login created for {child.first_name}.")
                return redirect("scheduler:child_detail", child_id=child.pk)

        elif "update_login_username" in request.POST:
            login_section_open = True
            if child.student_user is None:
                messages.error(request, "Create a student login first.")
                return redirect("scheduler:child_detail", child_id=child.pk)

            new_username = request.POST.get("new_username", "").strip()
            login_manage_data["new_username"] = new_username

            if not new_username:
                login_manage_errors["new_username"] = "Username is required."
            elif (
                User.objects.filter(username__iexact=new_username)
                .exclude(pk=child.student_user.pk)
                .exists()
            ):
                login_manage_errors["new_username"] = "This username is already taken."
            else:
                child.student_user.username = new_username
                child.student_user.save(update_fields=["username"])
                messages.success(
                    request,
                    f"{child.first_name}'s login username was updated.",
                )
                return redirect("scheduler:child_detail", child_id=child.pk)

        elif "reset_login_password" in request.POST:
            login_section_open = True
            if child.student_user is None:
                messages.error(request, "Create a student login first.")
                return redirect("scheduler:child_detail", child_id=child.pk)

            new_password1 = request.POST.get("new_password1", "")
            new_password2 = request.POST.get("new_password2", "")

            if not new_password1:
                login_manage_errors["new_password1"] = "Password is required."
            elif new_password1 != new_password2:
                login_manage_errors["new_password2"] = "Passwords do not match."
            else:
                try:
                    validate_password(new_password1, user=child.student_user)
                except ValidationError as exc:
                    login_manage_errors["new_password1"] = " ".join(exc.messages)
                else:
                    child.student_user.set_password(new_password1)
                    child.student_user.save(update_fields=["password"])
                    messages.success(
                        request,
                        f"{child.first_name}'s password was reset.",
                    )
                    return redirect("scheduler:child_detail", child_id=child.pk)

        elif "enroll_courses" in request.POST:
            selected_ids_raw = request.POST.getlist("course_ids")
            available_courses_qs = Course.objects.filter(
                parent=request.user,
                is_archived=False,
            )
            courses_by_id = {course.id: course for course in available_courses_qs}

            selected_ids = []
            for value in selected_ids_raw:
                try:
                    course_id = int(value)
                except (TypeError, ValueError):
                    continue
                if course_id in courses_by_id and course_id not in selected_ids:
                    selected_ids.append(course_id)

            if not selected_ids:
                messages.error(request, "Select at least one course to enroll.")
                return redirect("scheduler:child_detail", child_id=child.pk)

            today = timezone.localdate()
            created_count = 0
            reactivated_count = 0
            already_active_count = 0

            for course_id in selected_ids:
                course = courses_by_id[course_id]
                existing_active = CourseEnrollment.objects.filter(
                    course=course,
                    child=child,
                    status="active",
                ).exists()
                if existing_active:
                    already_active_count += 1
                    continue

                latest_inactive = (
                    CourseEnrollment.objects.filter(course=course, child=child)
                    .exclude(status="active")
                    .order_by("-enrolled_at")
                    .first()
                )

                if latest_inactive is not None:
                    latest_inactive.status = "active"
                    latest_inactive.completed_school_year = ""
                    latest_inactive.completed_calendar_year = None
                    latest_inactive.completed_at = None
                    latest_inactive.days_of_week = (
                        latest_inactive.days_of_week
                        or course.default_days
                        or [0, 1, 2, 3, 4]
                    )
                    latest_inactive.save(
                        update_fields=[
                            "status",
                            "completed_school_year",
                            "completed_calendar_year",
                            "completed_at",
                            "days_of_week",
                        ]
                    )
                    reactivated_count += 1
                else:
                    CourseEnrollment.objects.create(
                        course=course,
                        child=child,
                        start_date=today,
                        days_of_week=course.default_days or [0, 1, 2, 3, 4],
                        status="active",
                    )
                    created_count += 1

            if created_count or reactivated_count:
                messages.success(
                    request,
                    (
                        f"Enrollment updated: {created_count} new, "
                        f"{reactivated_count} reactivated."
                    ),
                )
            elif already_active_count:
                messages.info(
                    request, "Selected courses are already active for this student."
                )

            return redirect("scheduler:child_detail", child_id=child.pk)

    enrolled_subjects = child.enrolled_subjects.filter(is_active=True)
    course_enrollments = child.course_enrollments.select_related("course").order_by(
        "-enrolled_at"
    )
    active_course_enrollments = list(course_enrollments.filter(status="active"))
    completed_course_enrollments = list(course_enrollments.filter(status="completed"))
    available_courses = list(
        Course.objects.filter(parent=request.user, is_archived=False).order_by("name")
    )
    active_course_ids = {
        enrollment.course_id for enrollment in active_course_enrollments
    }
    for course in available_courses:
        course.is_current_enrolled = course.id in active_course_ids

    total_days_attended = child.scheduled_lessons.filter(log__status="complete").count()

    return render(
        request,
        "scheduler/child_detail.html",
        {
            "child": child,
            "school_years": school_years,
            "login_form": login_form,
            "login_manage_errors": login_manage_errors,
            "login_manage_data": login_manage_data,
            "login_section_open": login_section_open,
            "info_errors": info_errors,
            "enrolled_subjects": enrolled_subjects,
            "active_course_enrollments": active_course_enrollments,
            "completed_course_enrollments": completed_course_enrollments,
            "available_courses": available_courses,
            "total_days_attended": total_days_attended,
        },
    )
