import re

from django.db import migrations, models


def backfill_source_subject_name(apps, schema_editor):
    EnrolledSubject = apps.get_model("scheduler", "EnrolledSubject")
    pattern = re.compile(r"^(?P<subject>.+) \(from (?P<year>.+)\)$")

    for enrolled in EnrolledSubject.objects.all().iterator():
        if enrolled.source_subject_name:
            continue
        match = pattern.match((enrolled.subject_name or "").strip())
        if not match:
            continue
        subject = match.group("subject").strip()
        if not subject:
            continue
        enrolled.source_subject_name = subject
        enrolled.save(update_fields=["source_subject_name"])


class Migration(migrations.Migration):

    dependencies = [
        ("scheduler", "0005_vacation"),
    ]

    operations = [
        migrations.AddField(
            model_name="enrolledsubject",
            name="source_subject_name",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.RunPython(
            backfill_source_subject_name,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
