from django.db import models


class Lesson(models.Model):
    """A single Oak National Academy lesson as imported from the curriculum CSV.

    Each record represents one lesson within a unit, associated with a key stage,
    subject, year group, and containing a direct link to the Oak lesson page.
    """

    key_stage = models.CharField(max_length=10, db_index=True)
    subject_name = models.CharField(max_length=100, db_index=True)
    programme_slug = models.CharField(max_length=200)
    year = models.CharField(max_length=20, db_index=True)
    unit_slug = models.CharField(max_length=200)
    unit_title = models.CharField(max_length=300)
    lesson_number = models.IntegerField()
    lesson_title = models.CharField(max_length=300)
    lesson_url = models.URLField(max_length=500)

    class Meta:
        ordering = ['key_stage', 'subject_name', 'unit_slug', 'lesson_number']
        verbose_name = 'Lesson'
        verbose_name_plural = 'Lessons'

    def __str__(self):
        return f'{self.subject_name} — {self.lesson_title} ({self.year})'
