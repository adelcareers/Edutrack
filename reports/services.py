"""PDF generation service for EduTrack reports.

Builds a PDF from a Report record and uploads it to Cloudinary.
"""

import io

import cloudinary.uploader
from django.template.loader import render_to_string
from xhtml2pdf import pisa

from tracker.models import LessonLog


def generate_pdf(report):
    """Generate a PDF for *report*, upload to Cloudinary, and return the secure URL.

    Queries all completed LessonLogs for the report's child within the date
    range, groups them by subject, renders the PDF template, converts it to
    PDF bytes via xhtml2pdf, and uploads the result to Cloudinary.

    The ``report.pdf_file`` field is updated with the Cloudinary public_id and
    the record is saved before returning.

    Returns:
        str: The Cloudinary secure URL for the generated PDF.
    """
    logs = (
        LessonLog.objects.filter(
            scheduled_lesson__child=report.child,
            scheduled_lesson__scheduled_date__gte=report.date_from,
            scheduled_lesson__scheduled_date__lte=report.date_to,
            status="complete",
        )
        .select_related(
            "scheduled_lesson__lesson",
            "scheduled_lesson__enrolled_subject",
        )
        .order_by(
            "scheduled_lesson__enrolled_subject__subject_name",
            "scheduled_lesson__scheduled_date",
        )
    )

    subjects = {}
    for log in logs:
        name = log.scheduled_lesson.enrolled_subject.subject_name
        if name not in subjects:
            subjects[name] = {
                "name": name,
                "total": 0,
                "green": 0,
                "amber": 0,
                "red": 0,
                "unset": 0,
                "logs": [],
            }
        s = subjects[name]
        s["total"] += 1
        s[log.mastery] += 1
        s["logs"].append(log)

    context = {
        "report": report,
        "child": report.child,
        "subjects": list(subjects.values()),
    }

    html = render_to_string("reports/pdf_template.html", context)

    pdf_buffer = io.BytesIO()
    pisa.CreatePDF(html, dest=pdf_buffer)
    pdf_buffer.seek(0)

    public_id = f"reports/report_{report.id}_{report.child.first_name}_{report.date_from}".replace(
        " ", "_"
    )
    result = cloudinary.uploader.upload(
        pdf_buffer.read(),
        public_id=public_id,
        resource_type="raw",
        format="pdf",
    )

    report.pdf_file = result["public_id"]
    report.save(update_fields=["pdf_file"])

    return result["secure_url"]
