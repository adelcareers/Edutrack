from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_alter_userprofile_role"),
    ]

    operations = [
        migrations.AddField(
            model_name="parentsettings",
            name="receipt_enforcement_mode",
            field=models.CharField(
                choices=[
                    ("soft", "Soft reminder (allow completion with warning)"),
                    (
                        "hard",
                        "Hard required (student cannot complete without valid receipt)",
                    ),
                ],
                default="soft",
                max_length=10,
            ),
        ),
    ]
