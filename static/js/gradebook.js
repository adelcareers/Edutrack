(function () {
  'use strict';

  const modalEl = document.getElementById('gradeModal');
  if (!modalEl) {
    return;
  }

  const modal = new bootstrap.Modal(modalEl);

  const modalTitle = document.getElementById('gradeModalTitle');
  const modalSubTitle = document.getElementById('gradeModalSubTitle');
  const modalStatusBadge = document.getElementById('gradeModalStatusBadge');

  const assignmentIdInput = document.getElementById('gradeAssignmentId');
  const statusInput = document.getElementById('gradeStatusInput');
  const dueDateInput = document.getElementById('gradeDueDateInput');
  const scoreInput = document.getElementById('gradeScoreInput');
  const pointsInput = document.getElementById('gradePointsInput');
  const percentInput = document.getElementById('gradePercentInput');
  const notesInput = document.getElementById('gradeNotesInput');
  const editLink = document.getElementById('gradeEditLink');

  function getStatusMeta(status) {
    if (status === 'complete') {
      return { label: 'Complete', className: 'bg-success' };
    }
    if (status === 'overdue') {
      return { label: 'Overdue', className: 'bg-danger' };
    }
    return { label: 'Pending', className: 'text-bg-secondary' };
  }

  function openFromRow(row) {
    const status = row.dataset.displayStatus || row.dataset.status || 'pending';
    const statusMeta = getStatusMeta(status);

    modalTitle.textContent = row.dataset.assignmentName || 'Assignment';
    modalSubTitle.textContent = [
      row.dataset.assignmentCourse,
      row.dataset.assignmentType,
    ].filter(Boolean).join(' • ');

    modalStatusBadge.className = `badge ${statusMeta.className}`;
    modalStatusBadge.textContent = statusMeta.label;

    assignmentIdInput.value = row.dataset.assignmentId || '';
    statusInput.value = row.dataset.status || 'pending';
    dueDateInput.value = row.dataset.dueDate || '';
    scoreInput.value = row.dataset.score || '';
    pointsInput.value = row.dataset.points || '';
    percentInput.value = row.dataset.percent || '';
    notesInput.value = row.dataset.notes || '';

    const editUrl = row.dataset.editUrl || '#';
    editLink.setAttribute('href', editUrl);

    modal.show();
  }

  document.querySelectorAll('.gradebook-row').forEach((row) => {
    row.addEventListener('click', () => openFromRow(row));
    row.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        openFromRow(row);
      }
    });
  });
})();
