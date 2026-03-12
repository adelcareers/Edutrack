from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('scheduler', '0005_vacation'),
    ]

    operations = [
        migrations.CreateModel(
            name='Subject',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('parent', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='course_subjects', to='auth.user')),
            ],
            options={
                'ordering': ['name'],
                'unique_together': {('parent', 'name')},
            },
        ),
        migrations.CreateModel(
            name='Label',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('color', models.CharField(default='#6c757d', max_length=7)),
                ('parent', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='course_labels', to='auth.user')),
            ],
            options={
                'ordering': ['name'],
                'unique_together': {('parent', 'name')},
            },
        ),
        migrations.CreateModel(
            name='Course',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('color', models.CharField(default='#6c757d', max_length=7)),
                ('photo', models.ImageField(blank=True, null=True, upload_to='course_photos/')),
                ('grade_years', models.CharField(blank=True, default='', max_length=200)),
                ('duration_weeks', models.IntegerField(default=36, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(52)])),
                ('frequency_days', models.IntegerField(default=5, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(7)])),
                ('default_days', models.CharField(default='0,1,2,3,4', max_length=20)),
                ('grading_style', models.CharField(choices=[('not_graded', 'Not Graded'), ('point_graded', 'Point Graded'), ('percent_graded', 'Percent Graded')], default='not_graded', max_length=20)),
                ('use_assignment_weights', models.BooleanField(default=False)),
                ('credits', models.DecimalField(blank=True, decimal_places=1, max_digits=4, null=True)),
                ('description', models.TextField(blank=True, default='')),
                ('course_intro', models.TextField(blank=True, default='')),
                ('is_archived', models.BooleanField(db_index=True, default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('labels', models.ManyToManyField(blank=True, related_name='courses', to='courses.label')),
                ('parent', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='courses', to='auth.user')),
                ('subjects', models.ManyToManyField(blank=True, related_name='courses', to='courses.subject')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='AssignmentType',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('weight', models.IntegerField(default=0, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(100)])),
                ('order', models.IntegerField(default=0)),
                ('course', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='assignment_types', to='courses.course')),
            ],
            options={
                'ordering': ['order', 'name'],
            },
        ),
        migrations.CreateModel(
            name='CourseEnrollment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('start_date', models.DateField()),
                ('days_of_week', models.CharField(default='0,1,2,3,4', max_length=20)),
                ('status', models.CharField(choices=[('active', 'Active'), ('completed', 'Completed'), ('unenrolled', 'Unenrolled')], db_index=True, default='active', max_length=20)),
                ('completed_school_year', models.CharField(blank=True, default='', max_length=20)),
                ('completed_calendar_year', models.IntegerField(blank=True, null=True)),
                ('enrolled_at', models.DateTimeField(auto_now_add=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('child', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='course_enrollments', to='scheduler.child')),
                ('course', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='enrollments', to='courses.course')),
            ],
            options={
                'ordering': ['-enrolled_at'],
            },
        ),
    ]
