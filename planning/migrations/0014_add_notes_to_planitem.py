from django.db import migrations, models


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
    ]
