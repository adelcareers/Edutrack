from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from scheduler.models import ScheduledLesson
from tracker.models import EvidenceFile, LessonComment, LessonLog

from .lessons import _can_access_student_lesson

_ALLOWED_EVIDENCE_TYPES = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
        "image/svg+xml",
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
)


@login_required
@require_POST
def upload_evidence_view(request, scheduled_id):
    """Accept a multipart POST with a 'file' field and store it on Cloudinary.

    Validates ownership and restricts uploads to images, PDF, .doc, .docx.
    Creates a LessonLog if one does not yet exist.
    Returns JSON: {success, file_id, filename, uploaded_at}.
    """
    sl = get_object_or_404(ScheduledLesson, pk=scheduled_id)

    if not _can_access_student_lesson(request.user, sl):
        return JsonResponse({"error": "forbidden"}, status=403)

    uploaded_file = request.FILES.get("file")
    if not uploaded_file:
        return JsonResponse({"error": "no file provided"}, status=400)

    content_type = (uploaded_file.content_type or "").split(";")[0].strip().lower()
    if not (
        content_type.startswith("image/") or content_type in _ALLOWED_EVIDENCE_TYPES
    ):
        return JsonResponse({"error": "invalid file type"}, status=400)

    log, _ = LessonLog.objects.get_or_create(scheduled_lesson=sl)
    try:
        evidence = EvidenceFile.objects.create(
            lesson_log=log,
            file=uploaded_file,
            original_filename=uploaded_file.name,
            uploaded_by=request.user,
        )
    except Exception as exc:
        return JsonResponse(
            {"success": False, "error": f"Upload failed: {exc}"}, status=500
        )

    return JsonResponse(
        {
            "success": True,
            "file_id": evidence.pk,
            "filename": evidence.original_filename,
            "uploaded_at": evidence.uploaded_at.strftime("%d %b %Y"),
            "evidence_count": log.evidence_files.count(),
        }
    )


@login_required
@require_POST
def delete_evidence_view(request, file_id):
    """Delete an evidence file from Cloudinary and the database.

    Only the student who uploaded the file may delete it.
    Returns JSON: {success, evidence_count}.
    """
    import cloudinary.uploader

    evidence = get_object_or_404(EvidenceFile, pk=file_id)
    sl = evidence.lesson_log.scheduled_lesson
    if not _can_access_student_lesson(request.user, sl):
        return JsonResponse({"error": "forbidden"}, status=403)

    public_id = (
        evidence.file.public_id
        if hasattr(evidence.file, "public_id")
        else str(evidence.file)
    )
    try:
        cloudinary.uploader.destroy(public_id, resource_type="raw")
    except Exception:
        pass  # best-effort; always delete DB record

    log = evidence.lesson_log
    evidence.delete()

    return JsonResponse(
        {
            "success": True,
            "evidence_count": log.evidence_files.count(),
        }
    )


@login_required
@require_POST
def add_lesson_comment_view(request, scheduled_id):
    """Create a lesson comment for parent/student journal discussion."""
    sl = get_object_or_404(ScheduledLesson, pk=scheduled_id)

    if not _can_access_student_lesson(request.user, sl):
        return JsonResponse({"error": "forbidden"}, status=403)

    body = (request.POST.get("body") or "").strip()
    if not body:
        return JsonResponse({"error": "comment required"}, status=400)
    if len(body) > 2000:
        return JsonResponse({"error": "comment too long"}, status=400)

    comment = LessonComment.objects.create(
        scheduled_lesson=sl,
        author=request.user,
        body=body,
    )

    return JsonResponse(
        {
            "success": True,
            "comment": {
                "id": comment.pk,
                "author": comment.author.get_username(),
                "body": comment.body,
                "created_at": timezone.localtime(comment.created_at).strftime(
                    "%d %b %Y, %H:%M"
                ),
            },
            "comments_count": sl.comments.count(),
        }
    )
