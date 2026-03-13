from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('courses', '0003_globalassignmenttype'),
    ]

    operations = [
        migrations.CreateModel(
            name='CourseAssignmentType',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('color', models.CharField(default='#9ca3af', max_length=7)),
                ('is_hidden', models.BooleanField(default=False)),
                ('order', models.IntegerField(default=0)),
                ('course', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='assignment_type_overrides', to='courses.course')),
                ('global_type', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='courses.globalassignmenttype')),
            ],
            options={
                'ordering': ['order', 'name'],
                'unique_together': {('course', 'name')},
            },
        ),
        migrations.CreateModel(
            name='CourseAssignmentTemplate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('description', models.TextField(blank=True, default='')),
                ('is_graded', models.BooleanField(default=False)),
                ('due_offset_days', models.IntegerField(default=0)),
                ('order', models.IntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('assignment_type', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='templates', to='planning.courseassignmenttype')),
                ('course', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='assignment_templates', to='courses.course')),
            ],
            options={
                'ordering': ['order', 'name'],
            },
        ),
        migrations.CreateModel(
            name='AssignmentPlanItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('week_number', models.PositiveSmallIntegerField()),
                ('day_number', models.PositiveSmallIntegerField()),
                ('due_in_days', models.PositiveSmallIntegerField(default=0)),
                ('order', models.IntegerField(default=0)),
                ('notes', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('course', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='assignment_plan_items', to='courses.course')),
                ('template', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='plan_items', to='planning.courseassignmenttemplate')),
            ],
            options={
                'ordering': ['week_number', 'day_number', 'order'],
            },
        ),
        migrations.CreateModel(
            name='StudentAssignment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('due_date', models.DateField()),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('complete', 'Complete'), ('overdue', 'Overdue')], default='pending', max_length=20)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('score', models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('enrollment', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='assignments', to='courses.courseenrollment')),
                ('plan_item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='student_assignments', to='planning.assignmentplanitem')),
            ],
            options={
                'ordering': ['due_date', 'status'],
            },
        ),
    ]
