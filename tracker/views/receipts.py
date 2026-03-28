import re
from urllib.parse import unquote, urlparse

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import ParentSettings
from scheduler.models import ScheduledLesson
from tracker.models import LessonLog

from .lessons import _can_access_student_lesson


def _parse_receipt_metadata(receipt_url):
    """Extract lightweight preview metadata from a completion receipt URL."""
    parsed = urlparse(receipt_url)
    path_parts = [p for p in parsed.path.split("/") if p]
    lesson_slug = ""
    result_token = ""

    if "lessons" in path_parts:
        lesson_idx = path_parts.index("lessons")
        if len(path_parts) > lesson_idx + 1:
            lesson_slug = path_parts[lesson_idx + 1]
    if "results" in path_parts:
        result_idx = path_parts.index("results")
        if len(path_parts) > result_idx + 1:
            result_token = path_parts[result_idx + 1]

    title = ""
    if lesson_slug:
        title = unquote(lesson_slug).replace("-", " ").strip().title()

    return {
        "provider": parsed.netloc,
        "path": parsed.path,
        "lesson_title_guess": title,
        "result_token": result_token,
        "shared": parsed.path.rstrip("/").endswith("/share"),
    }


def _normalize_text_tokens(text):
    normalized = re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()
    tokens = [token for token in normalized.split() if len(token) > 2]
    stop_words = {
        "and",
        "for",
        "with",
        "from",
        "that",
        "this",
        "lesson",
        "unit",
        "year",
        "the",
        "are",
    }
    return [token for token in tokens if token not in stop_words]


def _receipt_matches_lesson(receipt_url, lesson_title):
    title_tokens = _normalize_text_tokens(lesson_title)
    url_text = re.sub(r"[^a-z0-9]+", " ", (receipt_url or "").lower())

    if not title_tokens:
        return {
            "matches": False,
            "reason": "lesson title missing",
            "matched_tokens": [],
            "required_tokens": [],
        }

    matched = [token for token in title_tokens if token in url_text]
    return {
        "matches": len(matched) == len(title_tokens),
        "reason": (
            "ok"
            if len(matched) == len(title_tokens)
            else "receipt link does not match lesson title"
        ),
        "matched_tokens": matched,
        "required_tokens": title_tokens,
    }


def _receipt_validation_status_for_log(log, lesson_title):
    if log is None or not log.completion_receipt_url:
        return {
            "has_link": False,
            "is_match": False,
            "state": "missing",
            "message": "Receipt link not attached.",
        }

    meta = log.completion_receipt_meta or {}
    if "title_match" in meta:
        is_match = bool(meta.get("title_match"))
    else:
        match_info = _receipt_matches_lesson(log.completion_receipt_url, lesson_title)
        is_match = bool(match_info["matches"])

    if is_match:
        return {
            "has_link": True,
            "is_match": True,
            "state": "matched",
            "message": "Receipt link matched this lesson.",
        }

    return {
        "has_link": True,
        "is_match": False,
        "state": "mismatch",
        "message": "Receipt link is attached but does not match this lesson.",
    }


def _receipt_enforcement_mode_for_lesson(sl):
    settings, _ = ParentSettings.objects.get_or_create(user=sl.child.parent)
    return settings.receipt_enforcement_mode or "soft"


@login_required
@require_POST
def save_receipt_link_view(request, scheduled_id):
    """Save a completion receipt URL and lightweight parsed metadata."""
    sl = get_object_or_404(ScheduledLesson, pk=scheduled_id)

    if not _can_access_student_lesson(request.user, sl):
        return JsonResponse({"error": "forbidden"}, status=403)

    receipt_url = (request.POST.get("receipt_url") or "").strip()
    meta = {}
    if receipt_url:
        parsed = urlparse(receipt_url)
        if not parsed.scheme or not parsed.netloc:
            return JsonResponse({"error": "invalid receipt url"}, status=400)

        title_match = _receipt_matches_lesson(receipt_url, sl.lesson.lesson_title)
        if not title_match["matches"]:
            return JsonResponse(
                {
                    "error": ("Receipt link does not match this lesson title."),
                    "match_detail": title_match,
                },
                status=400,
            )

        meta = _parse_receipt_metadata(receipt_url)
        meta["title_match"] = title_match["matches"]
        meta["title_match_reason"] = title_match["reason"]
        meta["title_match_tokens"] = title_match["matched_tokens"]
        meta["title_required_tokens"] = title_match["required_tokens"]

    log, _ = LessonLog.objects.get_or_create(scheduled_lesson=sl)
    log.completion_receipt_url = receipt_url
    log.completion_receipt_meta = meta
    if receipt_url:
        log.status = "complete"
        log.completed_at = timezone.now()
        log.save(
            update_fields=[
                "completion_receipt_url",
                "completion_receipt_meta",
                "status",
                "completed_at",
            ]
        )
    else:
        log.save(update_fields=["completion_receipt_url", "completion_receipt_meta"])

    return JsonResponse(
        {
            "success": True,
            "completion_receipt_url": log.completion_receipt_url,
            "completion_receipt_meta": log.completion_receipt_meta,
            "status": log.status,
            "message": (
                "Receipt saved and lesson marked complete."
                if receipt_url
                else "Receipt cleared."
            ),
        }
    )
