from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("planning", "0009_template_item_kind_and_nullable_assignment_type"),
        ("scheduler", "0006_enrolledsubject_source_subject_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="assignmentplanitem",
            name="lesson_child",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name="lesson_plan_items",
                to="scheduler.child",
            ),
        ),
        migrations.AddField(
            model_name="assignmentplanitem",
            name="lesson_enrolled_subject",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name="lesson_plan_items",
                to="scheduler.enrolledsubject",
            ),
        ),
        migrations.AddField(
            model_name="assignmentplanitem",
            name="scheduled_lesson",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name="plan_items",
                to="scheduler.scheduledlesson",
            ),
        ),
    ]
