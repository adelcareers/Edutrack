(function () {
  'use strict';

  const modalEl = document.getElementById('gradeModal');
  if (!modalEl) {
    return;
  }
  const role = modalEl.dataset.role || 'parent';
  const canGrade = modalEl.dataset.canGrade === 'true';

  const modal = new bootstrap.Modal(modalEl);

  const modalTitle = document.getElementById('gradeModalTitle');
  const modalSubTitle = document.getElementById('gradeModalSubTitle');
  const dateLabel = document.getElementById('gradeDateLabel');
  const weekDayLabel = document.getElementById('gradeWeekDayLabel');
  const descriptionLabel = document.getElementById('gradeDescription');
  const studentInitial = document.getElementById('gradeStudentInitial');
  const studentName = document.getElementById('gradeStudentName');
  const courseBadge = document.getElementById('gradeCourseBadge');
  const typeBadge = document.getElementById('gradeTypeBadge');
  const stateIcon = document.getElementById('gradeStateIcon');

  const assignmentIdInput = document.getElementById('gradeAssignmentId');
  const gradeModalForm = document.getElementById('gradeModalForm');
  const statusInput = document.getElementById('gradeStatusInput');
  const dueDateInput = document.getElementById('gradeDueDateInput');
  const scoreInput = document.getElementById('gradeScoreInput');
  const pointsInput = document.getElementById('gradePointsInput');
  const percentInput = document.getElementById('gradePercentInput');
  const notesInput = document.getElementById('gradeNotesInput');
  const footerSaveBtn = document.getElementById('gradeFooterSaveBtn');
  const editLink = document.getElementById('gradeEditLink');
  const quickCompleteBtn = document.getElementById('gradeQuickComplete');
  const quickRescheduleBtn = document.getElementById('gradeQuickReschedule');
  const quickEditBtn = document.getElementById('gradeQuickEdit');
  const stateLabel = document.getElementById('gradeWindowStateLabel');
  const attachmentsList = document.getElementById('gradeAttachmentsList');
  const commentsList = document.getElementById('gradeCommentsList');
  const submissionsList = document.getElementById('gradeSubmissionsList');
  const attachmentsTabBtn = document.getElementById('tabAttachmentsBtn');
  const commentsTabBtn = document.getElementById('tabCommentsBtn');
  const submissionsTabBtn = document.getElementById('tabSubmissionsBtn');
  const commentForm = document.getElementById('gradeCommentForm');
  const submissionForm = document.getElementById('gradeSubmissionForm');
  const studentScoreText = document.getElementById('studentScoreText');
  const studentPointsText = document.getElementById('studentPointsText');
  const studentPercentText = document.getElementById('studentPercentText');
  const studentStatusForm = document.getElementById('studentStatusForm');
  const studentStatusValue = document.getElementById('studentStatusValue');
  const studentToggleStatusLabel = document.getElementById('studentToggleStatusLabel');

  function getStatusMeta(status) {
    if (status === 'complete') {
      return {
        iconClass: 'bi-check-circle',
        iconColor: '#16a34a',
        label: 'Complete',
        labelColor: '#3f3f46',
      };
    }
    if (status === 'overdue') {
      return {
        iconClass: 'bi-exclamation-circle',
        iconColor: '#dc2626',
        label: 'Overdue',
        labelColor: '#3f3f46',
      };
    }
    if (status === 'needs_grading') {
      return {
        iconClass: 'bi-hourglass-split',
        iconColor: '#d97706',
        label: 'Needs Grading',
        labelColor: '#3f3f46',
      };
    }
    return {
      iconClass: 'bi-circle',
      iconColor: '#9ca3af',
      label: 'Incomplete',
      labelColor: '#8f8f93',
    };
  }

  function ordinal(n) {
    const mod10 = n % 10;
    const mod100 = n % 100;
    if (mod10 === 1 && mod100 !== 11) {
      return `${n}st`;
    }
    if (mod10 === 2 && mod100 !== 12) {
      return `${n}nd`;
    }
    if (mod10 === 3 && mod100 !== 13) {
      return `${n}rd`;
    }
    return `${n}th`;
  }

  function formatDueDate(value) {
    if (!value) {
      return 'Due date not set';
    }
    const date = new Date(`${value}T12:00:00`);
    if (Number.isNaN(date.getTime())) {
      return 'Due date not set';
    }
    const weekday = date.toLocaleDateString(undefined, { weekday: 'long' });
    const month = date.toLocaleDateString(undefined, { month: 'short' });
    return `Due ${weekday}, ${month} ${ordinal(date.getDate())}`;
  }

  function setState(status) {
    const statusMeta = getStatusMeta(status);
    if (stateLabel) {
      stateLabel.textContent = statusMeta.label;
      stateLabel.style.color = statusMeta.labelColor;
    }
    if (stateIcon) {
      stateIcon.className = `bi ${statusMeta.iconClass}`;
      stateIcon.style.color = statusMeta.iconColor;
    }
  }

  function setTabCounts(row) {
    const attachmentCount = row.dataset.attachmentsCount || '0';
    const commentCount = row.dataset.commentsCount || '0';
    const submissionCount = row.dataset.submissionsCount || '0';

    if (attachmentsTabBtn) {
      attachmentsTabBtn.textContent = `Attachments (${attachmentCount})`;
    }
    if (commentsTabBtn) {
      commentsTabBtn.textContent = `Comments (${commentCount})`;
    }
    if (submissionsTabBtn) {
      submissionsTabBtn.textContent = `Submissions (${submissionCount})`;
    }
  }

  function setStudentStatusAction(row) {
    if (!studentStatusForm || !studentStatusValue || !studentToggleStatusLabel) {
      return;
    }
    studentStatusForm.setAttribute('action', row.dataset.statusUrl || '#');
    const currentStatus = row.dataset.status || 'pending';
    const isCompleteState = currentStatus === 'complete' || currentStatus === 'needs_grading';
    if (isCompleteState) {
      studentStatusValue.value = 'incomplete';
      studentToggleStatusLabel.textContent = 'Mark Incomplete';
    } else {
      studentStatusValue.value = 'done';
      studentToggleStatusLabel.textContent = 'Mark Complete';
    }
  }

  function setTabContent(row) {
    const attachmentHtml = row.querySelector('.assignment-attachments-html')?.innerHTML;
    const commentHtml = row.querySelector('.assignment-comments-html')?.innerHTML;
    const submissionHtml = row.querySelector('.assignment-submissions-html')?.innerHTML;

    if (attachmentsList) {
      attachmentsList.innerHTML =
        attachmentHtml || '<p class="grade-modal-empty mb-0">No attachments.</p>';
    }
    if (commentsList) {
      commentsList.innerHTML =
        commentHtml || '<p class="grade-modal-empty mb-0">No comments yet.</p>';
    }
    if (submissionsList) {
      submissionsList.innerHTML =
        submissionHtml || '<p class="grade-modal-empty mb-0">No submissions yet.</p>';
    }

    if (commentForm) {
      commentForm.setAttribute('action', row.dataset.commentUrl || '#');
    }
    if (submissionForm) {
      submissionForm.setAttribute('action', row.dataset.submissionUrl || '#');
      const canSubmit = row.dataset.canSubmit === 'true';
      submissionForm.classList.toggle('d-none', !canSubmit);
    }
  }

  function openFromRow(row) {
    const status = row.dataset.displayStatus || row.dataset.status || 'pending';

    modalTitle.textContent = row.dataset.assignmentName || 'Assignment';
    modalSubTitle.textContent = row.dataset.assignmentCourse || '';
    if (dateLabel) {
      dateLabel.textContent = formatDueDate(row.dataset.dueDate || '');
    }
    if (weekDayLabel) {
      const week = row.dataset.weekNumber;
      const day = row.dataset.dayNumber;
      weekDayLabel.textContent = week && day ? `Week ${week}, Day ${day}` : '';
    }
    if (descriptionLabel) {
      const descHtmlEl = row.querySelector('.assignment-description-html');
      if (descHtmlEl && descHtmlEl.innerHTML && descHtmlEl.innerHTML.trim()) {
        descriptionLabel.innerHTML = descHtmlEl.innerHTML;
      } else {
        descriptionLabel.textContent =
          row.dataset.assignmentDescription || 'No description available.';
      }
    }
    if (studentName) {
      studentName.textContent = row.dataset.studentName || 'Student';
    }
    if (studentInitial) {
      const name = row.dataset.studentName || 'Student';
      studentInitial.textContent = name.charAt(0).toUpperCase();
    }
    if (courseBadge) {
      courseBadge.textContent = row.dataset.assignmentCourse || 'Course';
    }
    if (typeBadge) {
      typeBadge.textContent = row.dataset.assignmentType || 'Type';
    }

    if (assignmentIdInput) {
      assignmentIdInput.value = row.dataset.assignmentId || '';
    }
    if (statusInput) {
      statusInput.value = row.dataset.status || 'pending';
    }
    if (dueDateInput) {
      dueDateInput.value = row.dataset.dueDate || '';
    }
    if (scoreInput) {
      scoreInput.value = row.dataset.score || '';
    }
    if (pointsInput) {
      pointsInput.value = row.dataset.points || '';
    }
    if (percentInput) {
      percentInput.value = row.dataset.percent || '';
    }
    if (notesInput) {
      notesInput.value = row.dataset.notes || '';
    }

    if (studentScoreText) {
      studentScoreText.textContent = row.dataset.score || '-';
    }
    if (studentPointsText) {
      studentPointsText.textContent = row.dataset.points || '-';
    }
    if (studentPercentText) {
      studentPercentText.textContent = row.dataset.percent
        ? `${row.dataset.percent}%`
        : '-';
    }

    if (editLink) {
      const editUrl = row.dataset.editUrl || '#';
      editLink.setAttribute('href', editUrl);
    }

    setTabCounts(row);
    setTabContent(row);
    setStudentStatusAction(row);
    setState(status);

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

    const openBtn = row.querySelector('.open-grade-modal');
    if (openBtn) {
      openBtn.addEventListener('click', (event) => {
        event.preventDefault();
        event.stopPropagation();
        openFromRow(row);
      });
    }
  });

  if (quickCompleteBtn) {
    quickCompleteBtn.addEventListener('click', () => {
      if (!statusInput) {
        return;
      }
      statusInput.value = 'complete';
      setState('complete');
    });
  }

  if (quickRescheduleBtn) {
    quickRescheduleBtn.addEventListener('click', () => {
      if (dueDateInput) {
        dueDateInput.focus();
        dueDateInput.showPicker?.();
      }
    });
  }

  if (quickEditBtn) {
    quickEditBtn.addEventListener('click', () => {
      if (!editLink) {
        return;
      }
      const editUrl = editLink.getAttribute('href');
      if (editUrl && editUrl !== '#') {
        window.open(editUrl, '_blank');
      }
    });
  }

  if (statusInput) {
    statusInput.addEventListener('change', () => {
      setState(statusInput.value || 'pending');
    });
  }

  if (footerSaveBtn && gradeModalForm) {
    footerSaveBtn.addEventListener('click', () => {
      gradeModalForm.requestSubmit();
    });
  }

  if (!canGrade && gradeModalForm) {
    gradeModalForm.addEventListener('submit', (event) => {
      event.preventDefault();
    });
  }

  if (role === 'student' && statusInput) {
    statusInput.disabled = true;
  }
})();
