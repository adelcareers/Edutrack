import datetime

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from scheduler.models import ScheduledLesson
from tracker.models import LessonComment, LessonLog


def _can_access_student_assignment(user, assignment):
    """Return True when user is parent of child or the student owner."""
    profile = getattr(user, "profile", None)
    if profile is None:
        return False

    if profile.role in {"parent", "teacher"}:
        return assignment.enrollment.course.parent_id == user.pk

    if profile.role == "student":
        child = getattr(user, "child_profile", None)
        return child is not None and assignment.enrollment.child_id == child.pk

    return False


def _can_access_student_lesson(user, scheduled_lesson):
    """Return True when user is parent of child or the student owner."""
    profile = getattr(user, "profile", None)
    if profile is None:
        return False

    if profile.role == "parent":
        return scheduled_lesson.child.parent_id == user.pk

    if profile.role == "student":
        child = getattr(user, "child_profile", None)
        return child is not None and scheduled_lesson.child_id == child.pk

    return False


def _effective_lesson_status(log, scheduled_date, today=None):
    """Return UI-facing status for a lesson card/modal."""
    if today is None:
        today = datetime.date.today()

    if log and log.status == "complete":
        return "complete"
    if log and log.status == "overdue":
        return "overdue"
    if log and log.status == "skipped":
        return "skipped"
    if scheduled_date < today:
        return "overdue"
    return "incomplete"


def _lesson_status_meta(status_key):
    """Map lesson status key to UI label/icon metadata."""
    status_map = {
        "complete": {
            "label": "Complete",
            "icon": "check-circle-fill",
            "tone": "success",
        },
        "overdue": {
            "label": "Overdue",
            "icon": "exclamation-triangle-fill",
            "tone": "danger",
        },
        "incomplete": {
            "label": "Incomplete",
            "icon": "dash-circle",
            "tone": "secondary",
        },
        "skipped": {"label": "Skipped", "icon": "skip-forward-circle", "tone": "dark"},
    }
    return status_map.get(status_key, status_map["incomplete"])


@login_required
def lesson_detail_view(request, scheduled_id):
    """Return JSON details for a single scheduled lesson.

    Ownership check: the lesson must belong to the student's child profile.
    """
    from .receipts import _receipt_enforcement_mode_for_lesson, _receipt_validation_status_for_log

    sl = get_object_or_404(ScheduledLesson, pk=scheduled_id)

    if not _can_access_student_lesson(request.user, sl):
        return JsonResponse({"error": "forbidden"}, status=403)

    log = getattr(sl, "log", None)
    status_key = _effective_lesson_status(log, sl.scheduled_date)
    status_meta = _lesson_status_meta(status_key)
    evidence_count = log.evidence_files.count() if log else 0
    evidence_files = (
        [
            {
                "id": ef.pk,
                "filename": ef.original_filename,
                "uploaded_at": ef.uploaded_at.strftime("%d %b %Y"),
            }
            for ef in log.evidence_files.all()
        ]
        if log
        else []
    )
    comments = list(sl.comments.select_related("author").all())
    iso = sl.scheduled_date.isocalendar()
    child_avatar = sl.child.photo.url if getattr(sl.child, "photo", None) else ""
    receipt_meta = log.completion_receipt_meta if log else {}
    receipt_status = _receipt_validation_status_for_log(log, sl.lesson.lesson_title)
    receipt_enforcement_mode = _receipt_enforcement_mode_for_lesson(sl)

    return JsonResponse(
        {
            "id": sl.pk,
            "lesson_title": sl.lesson.lesson_title,
            "unit_title": sl.lesson.unit_title,
            "lesson_key_stage": sl.lesson.key_stage.upper(),
            "lesson_year": sl.lesson.year,
            "subject_name": sl.enrolled_subject.subject_name,
            "scheduled_date": sl.scheduled_date.strftime("%d %b %Y"),
            "scheduled_date_iso": sl.scheduled_date.isoformat(),
            "week_number": iso.week,
            "day_number": iso.weekday,
            "lesson_url": sl.lesson.lesson_url,
            "colour_hex": sl.enrolled_subject.colour_hex,
            "status": status_key,
            "status_label": status_meta["label"],
            "status_icon": status_meta["icon"],
            "status_tone": status_meta["tone"],
            "mastery": log.mastery if log else "unset",
            "student_notes": log.student_notes if log else "",
            "student_name": sl.child.first_name,
            "student_avatar": child_avatar,
            "completion_receipt_url": log.completion_receipt_url if log else "",
            "completion_receipt_meta": receipt_meta,
            "receipt_status": receipt_status,
            "receipt_enforcement_mode": receipt_enforcement_mode,
            "evidence_count": evidence_count,
            "evidence_files": evidence_files,
            "submissions_count": evidence_count,
            "comments": [
                {
                    "id": comment.pk,
                    "author": comment.author.get_username(),
                    "body": comment.body,
                    "created_at": timezone.localtime(comment.created_at).strftime(
                        "%d %b %Y, %H:%M"
                    ),
                }
                for comment in comments
            ],
            "comments_count": len(comments),
        }
    )


@login_required
@require_POST
def update_lesson_status_view(request, scheduled_id):
    """Accept a POST lesson status and persist it to LessonLog.

    Ownership is verified: the lesson must belong to the authenticated
    student's child profile.  Returns JSON on both success and error.
    """
    from .receipts import _receipt_enforcement_mode_for_lesson, _receipt_validation_status_for_log

    sl = get_object_or_404(ScheduledLesson, pk=scheduled_id)

    if not _can_access_student_lesson(request.user, sl):
        return JsonResponse({"error": "forbidden"}, status=403)

    new_status = request.POST.get("status", "")
    if new_status not in ("complete", "overdue", "skipped", "pending"):
        return JsonResponse({"error": "invalid status"}, status=400)

    log, _ = LessonLog.objects.get_or_create(scheduled_lesson=sl)
    viewer_role = getattr(getattr(request.user, "profile", None), "role", None)
    enforcement_mode = _receipt_enforcement_mode_for_lesson(sl)
    receipt_status = _receipt_validation_status_for_log(log, sl.lesson.lesson_title)

    if (
        new_status == "complete"
        and viewer_role == "student"
        and enforcement_mode == "hard"
        and not (receipt_status["has_link"] and receipt_status["is_match"])
    ):
        return JsonResponse(
            {
                "error": (
                    "Receipt link is required and must match this lesson before "
                    "marking complete."
                )
            },
            status=400,
        )

    log.status = new_status
    if new_status == "complete":
        log.completed_at = timezone.now()
    else:
        log.completed_at = None
    log.save()

    message_map = {
        "complete": "Lesson marked as complete.",
        "overdue": "Lesson marked as overdue.",
        "skipped": "Lesson skipped.",
        "pending": "Lesson marked as pending.",
    }

    response = {
        "success": True,
        "status": log.status,
        "message": message_map.get(new_status, "Lesson status updated."),
        "receipt_enforcement_mode": enforcement_mode,
    }
    if (
        new_status == "complete"
        and viewer_role == "student"
        and enforcement_mode == "soft"
        and not (receipt_status["has_link"] and receipt_status["is_match"])
    ):
        response["warning"] = (
            "Completed with warning: receipt link is missing or does not match this lesson."
        )

    return JsonResponse(response)


@login_required
@require_POST
def update_mastery_view(request, scheduled_id):
    """Accept a POST {mastery: 'green'|'amber'|'red'} and persist it to LessonLog.

    Ownership is verified: the lesson must belong to the authenticated
    student's child profile.  Returns JSON on both success and error.
    """
    sl = get_object_or_404(ScheduledLesson, pk=scheduled_id)

    if not _can_access_student_lesson(request.user, sl):
        return JsonResponse({"error": "forbidden"}, status=403)

    new_mastery = request.POST.get("mastery", "")
    if new_mastery not in ("green", "amber", "red"):
        return JsonResponse({"error": "invalid mastery"}, status=400)

    log, _ = LessonLog.objects.get_or_create(scheduled_lesson=sl)
    log.mastery = new_mastery
    log.save()

    return JsonResponse(
        {
            "success": True,
            "mastery": log.mastery,
        }
    )


@login_required
@require_POST
def save_notes_view(request, scheduled_id):
    """Accept a POST {notes: string} and persist it to LessonLog.student_notes.

    Ownership is verified: the lesson must belong to the authenticated
    student's child profile.  Notes are capped at 1000 characters.
    Returns JSON on both success and error.
    """
    sl = get_object_or_404(ScheduledLesson, pk=scheduled_id)

    if not _can_access_student_lesson(request.user, sl):
        return JsonResponse({"error": "forbidden"}, status=403)

    notes = request.POST.get("notes", "")
    if len(notes) > 1000:
        return JsonResponse({"error": "notes too long"}, status=400)

    log, _ = LessonLog.objects.get_or_create(scheduled_lesson=sl)
    log.student_notes = notes
    log.save()

    return JsonResponse({"success": True, "student_notes": log.student_notes})


@login_required
@require_POST
def reschedule_lesson_view(request, scheduled_id):
    """Accept a POST {new_date: 'YYYY-MM-DD'} and move the lesson to that date.

    Ownership is verified.  new_date must be strictly in the future (> today).
    Updates ScheduledLesson.scheduled_date and LessonLog.rescheduled_to.
    Returns JSON on both success and error.
    """
    sl = get_object_or_404(ScheduledLesson, pk=scheduled_id)

    if not _can_access_student_lesson(request.user, sl):
        return JsonResponse({"error": "forbidden"}, status=403)

    raw_date = request.POST.get("new_date", "").strip()
    try:
        new_date = datetime.date.fromisoformat(raw_date)
    except ValueError:
        return JsonResponse({"error": "invalid date"}, status=400)

    if new_date <= datetime.date.today():
        return JsonResponse({"error": "date must be in the future"}, status=400)

    sl.scheduled_date = new_date
    sl.save()

    log, _ = LessonLog.objects.get_or_create(scheduled_lesson=sl)
    log.rescheduled_to = new_date
    log.save()

    return JsonResponse({"success": True, "new_date": new_date.isoformat()})


@login_required
@require_POST
def edit_scheduled_lesson_view(request, scheduled_id):
    """Edit scheduled lesson date and optional order on day."""
    sl = get_object_or_404(ScheduledLesson, pk=scheduled_id)

    if not _can_access_student_lesson(request.user, sl):
        return JsonResponse({"error": "forbidden"}, status=403)

    raw_date = (request.POST.get("scheduled_date") or "").strip()
    if not raw_date:
        return JsonResponse({"error": "scheduled_date required"}, status=400)
    try:
        new_date = datetime.date.fromisoformat(raw_date)
    except ValueError:
        return JsonResponse({"error": "invalid date"}, status=400)

    raw_order = (request.POST.get("order_on_day") or "").strip()
    if raw_order:
        try:
            sl.order_on_day = max(0, int(raw_order))
        except ValueError:
            return JsonResponse({"error": "invalid order"}, status=400)

    sl.scheduled_date = new_date
    sl.save(update_fields=["scheduled_date", "order_on_day"])
    return JsonResponse(
        {
            "success": True,
            "scheduled_date": sl.scheduled_date.isoformat(),
            "order_on_day": sl.order_on_day,
        }
    )


@login_required
@require_POST
def delete_scheduled_lesson_view(request, scheduled_id):
    """Delete a scheduled lesson entry from the calendar."""
    sl = get_object_or_404(ScheduledLesson, pk=scheduled_id)

    if not _can_access_student_lesson(request.user, sl):
        return JsonResponse({"error": "forbidden"}, status=403)

    sl.delete()
    return JsonResponse({"success": True})
