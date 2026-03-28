"""Vacation management views."""

import datetime

from django.contrib import messages
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import role_required
from scheduler.models import Child


@role_required("parent")
def manage_vacations_view(request, child_id):
    """List all vacations for a child and provide an inline add form."""
    from scheduler.models import Vacation

    child = get_object_or_404(Child, pk=child_id, parent=request.user)
    vacations = child.vacations.all()
    return render(
        request,
        "scheduler/manage_vacations.html",
        {
            "child": child,
            "vacations": vacations,
        },
    )


@role_required("parent")
def add_vacation_view(request, child_id):
    """Create a new vacation for a child via POST."""
    from scheduler.models import Vacation

    child = get_object_or_404(Child, pk=child_id, parent=request.user)

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        start_date_raw = request.POST.get("start_date", "").strip()
        end_date_raw = request.POST.get("end_date", "").strip()

        errors = []
        if not name:
            errors.append("Vacation name is required.")
        start_date = end_date = None
        try:
            start_date = datetime.date.fromisoformat(start_date_raw)
        except ValueError:
            errors.append("Start date is invalid.")
        try:
            end_date = datetime.date.fromisoformat(end_date_raw)
        except ValueError:
            errors.append("End date is invalid.")
        if start_date and end_date and end_date < start_date:
            errors.append("End date must be on or after start date.")

        if errors:
            for e in errors:
                messages.error(request, e)
        else:
            Vacation.objects.create(
                child=child,
                name=name,
                start_date=start_date,
                end_date=end_date,
            )
            messages.success(request, f'Vacation "{name}" added.')

    return redirect("scheduler:manage_vacations", child_id=child.pk)


@role_required("parent")
def delete_vacation_view(request, vacation_id):
    """Delete a vacation via POST (ownership verified via child.parent)."""
    from scheduler.models import Vacation

    vacation = get_object_or_404(Vacation, pk=vacation_id)
    child = vacation.child
    if child.parent_id != request.user.pk:
        return HttpResponseForbidden("You do not own this vacation.")
    if request.method == "POST":
        vacation.delete()
        messages.success(request, "Vacation deleted.")
    return redirect("scheduler:manage_vacations", child_id=child.pk)
