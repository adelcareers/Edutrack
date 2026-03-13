from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('courses', '0002_alter_course_photo'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='GlobalAssignmentType',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('color', models.CharField(default='#9ca3af', max_length=7)),
                ('is_hidden', models.BooleanField(default=False)),
                ('order', models.IntegerField(default=0)),
                ('parent', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='global_assignment_types', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['order', 'name'],
                'unique_together': {('parent', 'name')},
            },
        ),
    ]
