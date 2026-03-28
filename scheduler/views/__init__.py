"""Views package for the scheduler app — re-exports all public views."""

from scheduler.views.children import (
    child_detail_view,
    child_list_view,
    child_new_view,
    delete_child_view,
)
from scheduler.views.logins import create_student_login_view
from scheduler.views.schedule import generate_schedule_view, schedule_edit_view
from scheduler.views.subjects import (
    SUBJECT_COLOUR_PALETTE,
    custom_subject_view,
    schedule_days_view,
    subject_selection_view,
)
from scheduler.views.vacations import (
    add_vacation_view,
    delete_vacation_view,
    manage_vacations_view,
)

__all__ = [
    "SUBJECT_COLOUR_PALETTE",
    "child_list_view",
    "child_new_view",
    "delete_child_view",
    "child_detail_view",
    "subject_selection_view",
    "schedule_days_view",
    "custom_subject_view",
    "generate_schedule_view",
    "schedule_edit_view",
    "create_student_login_view",
    "manage_vacations_view",
    "add_vacation_view",
    "delete_vacation_view",
]
