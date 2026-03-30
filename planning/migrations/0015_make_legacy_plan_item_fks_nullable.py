from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("planning", "0013_activityprogress_new_plan_item_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="planitem",
            name="notes",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AlterField(
            model_name="studentassignment",
            name="plan_item",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="student_assignments",
                to="planning.assignmentplanitem",
            ),
        ),
        migrations.AlterField(
            model_name="activityprogress",
            name="plan_item",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="activity_progress_items",
                to="planning.assignmentplanitem",
            ),
        ),
    ]
