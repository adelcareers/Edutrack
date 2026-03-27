from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("planning", "0008_alter_studentassignment_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="courseassignmenttemplate",
            name="item_kind",
            field=models.CharField(
                choices=[
                    ("assignment", "Assignment"),
                    ("activity", "Activity"),
                    ("lesson", "Lesson"),
                ],
                default="assignment",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="courseassignmenttemplate",
            name="assignment_type",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.CASCADE,
                related_name="templates",
                to="courses.assignmenttype",
            ),
        ),
    ]
