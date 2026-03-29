# Generated migration for UserProfile tier and storage changes

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_alter_parentsettings_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="subscription_tier",
            field=models.CharField(
                choices=[("essential", "Essential"), ("premium", "Premium")],
                default="essential",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="storage_limit_gb",
            field=models.IntegerField(default=20),
        ),
    ]
