import re
for filename in ['scheduler/tests.py', 'tracker/tests.py', 'accounts/tests.py', 'reports/tests.py']:
    with open(filename, 'r') as f: text = f.read()
    text = text.replace('def test_count_matches_db_records', 'def test_schedule_generates_correct_count')
    text = text.replace('def test_no_lesson_falls_on_weekend', 'def test_no_weekend_lessons')
    text = text.replace('def test_no_subject_exceeds_weekly_pace', 'def test_respects_weekly_pace')
    text = text.replace('def test_mark_complete_creates_lessonlog', 'def test_lesson_log_created_on_complete')
    text = text.replace('def test_second_post_updates_existing_log', 'def test_status_update')
    text = text.replace('def test_register_valid_creates_user_and_profile', 'def test_registration_creates_parent_role')
