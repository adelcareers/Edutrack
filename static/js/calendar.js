/* EduTrack calendar modal interactions */

(function () {
  'use strict';

  const modal = document.getElementById('lesson-modal');
  const bsModal = modal ? new bootstrap.Modal(modal) : null;
  const modalTitle = document.getElementById('modal-title');
  const modalHdr = document.getElementById('modal-header');
  const modalSubj = document.getElementById('modal-subject');
  const modalDate = document.getElementById('modal-date');
  const modalUnit = document.getElementById('modal-unit');
  const modalInlineLink = document.getElementById('modal-inline-link');
  const modalStudentName = document.getElementById('modal-student-name');
  const modalStudentAvatar = document.getElementById('modal-student-avatar');
  const modalWeekday = document.getElementById('modal-weekday');
  const modalStatusChip = document.getElementById('modal-status-chip');
  const modalStatusIcon = document.getElementById('modal-status-icon');
  const modalStatusLabel = document.getElementById('modal-status-label');

  const modalNotes = document.getElementById('modal-notes');
  const notesCount = document.getElementById('notes-char-count');
  const btnSaveNotes = document.getElementById('modal-btn-save-notes');

  const receiptInput = document.getElementById('modal-receipt-url');
  const receiptPreview = document.getElementById('modal-receipt-preview');
  const btnSaveReceipt = document.getElementById('modal-btn-save-receipt');

  const commentsList = document.getElementById('modal-comments-list');
  const commentInput = document.getElementById('modal-comment-input');
  const btnAddComment = document.getElementById('modal-btn-add-comment');
  const commentsCountTab = document.getElementById('modal-comments-count-tab');

  const evidenceCount = document.getElementById('modal-evidence-count');
  const submissionsCountTab = document.getElementById('modal-submissions-count-tab');
  const evidenceList = document.getElementById('modal-evidence-list');
  const evidenceFile = document.getElementById('modal-evidence-file');
  const btnUpload = document.getElementById('modal-btn-upload');

  const rescheduleDate = document.getElementById('modal-reschedule-date');
  const btnComplete = document.getElementById('modal-btn-complete');
  const btnSkip = document.getElementById('modal-btn-skip');
  const btnReschedule = document.getElementById('modal-btn-reschedule');
  const btnEdit = document.getElementById('modal-btn-edit');
  const btnDelete = document.getElementById('modal-btn-delete');

  const assignmentModalEl = document.getElementById('assignment-modal');
  const assignmentModal = assignmentModalEl ? new bootstrap.Modal(assignmentModalEl) : null;
  const assignmentTitle = document.getElementById('assignment-modal-title');
  const assignmentCourse = document.getElementById('assignment-modal-course');
  const assignmentDue = document.getElementById('assignment-modal-due');
  const assignmentType = document.getElementById('assignment-modal-type');
  const assignmentNotes = document.getElementById('assignment-modal-notes');
  const assignmentStatus = document.getElementById('assignment-modal-status');
  const assignmentBtnDone = document.getElementById('assignment-btn-done');
  const assignmentBtnIncomplete = document.getElementById('assignment-btn-incomplete');

  let activeScheduledId = null;
  let activeAssignmentId = null;

  function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
    return null;
  }

  function showModalAlert(message, type) {
    const wrap = document.getElementById('modal-upload-alert-wrap');
    if (!wrap) return;
    wrap.innerHTML = '';
    const div = document.createElement('div');
    div.className = `alert alert-${type} py-1 px-2 mb-2 small`;
    div.textContent = message;
    wrap.appendChild(div);
  }

  function setLessonStatus(statusKey, label, icon, tone) {
    if (!modalStatusChip) return;
    modalStatusChip.className = `lesson-status-chip status-${tone || 'secondary'}`;
    if (modalStatusLabel) modalStatusLabel.textContent = label || statusKey;
    if (modalStatusIcon) modalStatusIcon.className = `bi bi-${icon || 'dash-circle'}`;
  }

  function setActiveMastery(mastery) {
    document.querySelectorAll('.mastery-btn').forEach((btn) => {
      btn.classList.toggle('mastery-active', btn.dataset.mastery === mastery);
    });
  }

  function updateCardBadge(scheduledId, status) {
    const card = document.querySelector(`.lesson-card[data-id="${scheduledId}"]`);
    if (!card) return;
    const footer = card.querySelector('.card-footer');
    if (!footer) return;

    const labelMap = {
      complete: 'Complete',
      skipped: 'Skipped',
      overdue: 'Overdue',
      incomplete: 'Incomplete',
    };
    const classMap = {
      complete: 'bg-success',
      skipped: 'bg-secondary',
      overdue: 'bg-danger',
      incomplete: 'bg-light text-dark',
    };
    const existingBadge = footer.querySelector('.status-badge');
    const label = labelMap[status] || status;
    const cls = classMap[status] || 'bg-light text-dark';

    if (existingBadge) {
      existingBadge.textContent = label;
      existingBadge.className = `badge status-badge ${cls} me-1`;
    } else {
      const badge = document.createElement('span');
      badge.className = `badge status-badge ${cls} me-1`;
      badge.textContent = label;
      footer.prepend(badge);
    }
  }

  function updateCardMastery(scheduledId, mastery) {
    const card = document.querySelector(`.lesson-card[data-id="${scheduledId}"]`);
    if (!card) return;
    const footer = card.querySelector('.card-footer');
    if (!footer) return;

    const existing = footer.querySelector('.mastery-dot');
    if (existing) existing.remove();
    if (mastery && mastery !== 'unset') {
      const dot = document.createElement('span');
      dot.className = `mastery-dot ${mastery}`;
      footer.appendChild(dot);
    }
  }

  function renderEvidenceList(files) {
    if (!evidenceList) return;
    evidenceList.innerHTML = '';
    (files || []).forEach((f) => {
      const li = document.createElement('li');
      li.dataset.fileId = f.id;
      li.className = 'd-flex justify-content-between align-items-center py-1';
      li.innerHTML = `<span class="text-truncate me-2">${f.filename} <span class="text-muted">(${f.uploaded_at})</span></span>
        <button class="btn btn-sm btn-outline-danger btn-delete-evidence py-0 px-1" data-fid="${f.id}" type="button">&times;</button>`;
      evidenceList.appendChild(li);
    });
  }

  function renderComments(comments) {
    if (!commentsList) return;
    commentsList.innerHTML = '';
    if (!comments || !comments.length) {
      const empty = document.createElement('div');
      empty.className = 'text-muted small';
      empty.textContent = 'No comments yet.';
      commentsList.appendChild(empty);
      return;
    }

    comments.forEach((comment) => {
      const el = document.createElement('div');
      el.className = 'comment-entry';
      el.innerHTML = `<div class="comment-meta">${comment.author} • ${comment.created_at}</div>
        <div>${comment.body}</div>`;
      commentsList.appendChild(el);
    });
  }

  function appendComment(comment) {
    if (!commentsList || !comment) return;
    const empty = commentsList.querySelector('.text-muted.small');
    if (empty) empty.remove();
    const el = document.createElement('div');
    el.className = 'comment-entry';
    el.innerHTML = `<div class="comment-meta">${comment.author} • ${comment.created_at}</div>
      <div>${comment.body}</div>`;
    commentsList.appendChild(el);
    commentsList.scrollTop = commentsList.scrollHeight;
  }

  function renderReceiptPreview(meta) {
    if (!receiptPreview) return;
    if (!meta || !Object.keys(meta).length) {
      receiptPreview.style.display = 'none';
      receiptPreview.innerHTML = '';
      return;
    }

    const lessonGuess = meta.lesson_title_guess || 'Unknown lesson';
    const provider = meta.provider || 'Unknown provider';
    const token = meta.result_token || 'n/a';
    receiptPreview.style.display = 'block';
    receiptPreview.innerHTML = `<div><strong>Provider:</strong> ${provider}</div>
      <div><strong>Lesson:</strong> ${lessonGuess}</div>
      <div><strong>Result token:</strong> ${token}</div>`;
  }

  function activateLessonTab(tabName) {
    document.querySelectorAll('.lesson-tab-btn').forEach((btn) => {
      btn.classList.toggle('active', btn.dataset.tab === tabName);
    });
    document.querySelectorAll('.lesson-tab-pane').forEach((pane) => {
      pane.classList.toggle('active', pane.dataset.pane === tabName);
    });
  }

  async function postForm(url, payload) {
    const body = new URLSearchParams(payload || {});
    const resp = await fetch(url, {
      method: 'POST',
      headers: {
        'X-CSRFToken': getCookie('csrftoken'),
        'X-Requested-With': 'XMLHttpRequest',
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      credentials: 'same-origin',
      body,
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.error || `HTTP ${resp.status}`);
    return data;
  }

  async function openLessonModal(scheduledId) {
    activeScheduledId = scheduledId;
    try {
      const resp = await fetch(`/lessons/${scheduledId}/detail/`, {
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        credentials: 'same-origin',
      });
      if (!resp.ok) return;
      const data = await resp.json();

      if (modalHdr) {
        modalHdr.style.setProperty('--modal-colour', data.colour_hex || '#6c757d');
      }
      if (modalTitle) modalTitle.textContent = data.lesson_title || 'Lesson Detail';
      if (modalSubj) modalSubj.textContent = data.subject_name || '';
      if (modalDate) modalDate.textContent = data.scheduled_date || '';
      if (modalUnit) modalUnit.textContent = data.unit_title ? `Unit: ${data.unit_title}` : '';
      if (modalInlineLink) modalInlineLink.href = data.lesson_url || '#';

      if (modalStudentName) modalStudentName.textContent = data.student_name || 'Student';
      if (modalWeekday) {
        modalWeekday.textContent = `Week ${data.week_number || 0}, Day ${data.day_number || 0}`;
      }
      if (modalStudentAvatar) {
        const initial = (data.student_name || 'S').slice(0, 1).toUpperCase();
        if (data.student_avatar) {
          modalStudentAvatar.innerHTML = `<img src="${data.student_avatar}" alt="Student avatar">`;
        } else {
          modalStudentAvatar.textContent = initial;
        }
      }

      setLessonStatus(data.status, data.status_label, data.status_icon, data.status_tone);
      setActiveMastery(data.mastery || 'unset');

      if (modalNotes) {
        modalNotes.value = data.student_notes || '';
        if (notesCount) notesCount.textContent = modalNotes.value.length;
      }

      if (rescheduleDate) {
        rescheduleDate.value = data.scheduled_date_iso || '';
      }

      if (receiptInput) receiptInput.value = data.completion_receipt_url || '';
      renderReceiptPreview(data.completion_receipt_meta || {});

      if (evidenceCount) evidenceCount.textContent = data.evidence_count ?? 0;
      if (submissionsCountTab) submissionsCountTab.textContent = data.submissions_count ?? 0;
      renderEvidenceList(data.evidence_files || []);

      if (commentsCountTab) commentsCountTab.textContent = data.comments_count ?? 0;
      renderComments(data.comments || []);
      activateLessonTab('overview');

      if (bsModal) bsModal.show();
    } catch (e) {
      showModalAlert('Could not open lesson details.', 'danger');
    }
  }

  async function openAssignmentModal(assignmentId) {
    activeAssignmentId = assignmentId;
    try {
      const resp = await fetch(`/assignments/${assignmentId}/detail/`, {
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        credentials: 'same-origin',
      });
      if (!resp.ok) return;
      const data = await resp.json();

      if (assignmentTitle) assignmentTitle.textContent = data.assignment_name;
      if (assignmentCourse) assignmentCourse.textContent = `${data.course_name} • ${data.child_name}`;
      if (assignmentDue) assignmentDue.textContent = `Due: ${data.due_date}`;
      if (assignmentType) assignmentType.textContent = data.assignment_type;
      if (assignmentNotes) assignmentNotes.textContent = data.notes || '';
      if (assignmentStatus) {
        const statusMap = {
          done: ['Done', 'bg-success'],
          incomplete: ['Incomplete', 'text-bg-secondary'],
          overdue: ['Overdue', 'bg-danger'],
        };
        const statusInfo = statusMap[data.effective_status] || statusMap.incomplete;
        assignmentStatus.textContent = statusInfo[0];
        assignmentStatus.className = `badge ms-1 ${statusInfo[1]}`;
      }

      if (assignmentModal) assignmentModal.show();
    } catch (e) {
      // silent fail
    }
  }

  document.querySelectorAll('.lesson-card').forEach((card) => {
    card.addEventListener('click', () => {
      const id = card.dataset.id;
      if (id) openLessonModal(id);
    });
    card.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        const id = card.dataset.id;
        if (id) openLessonModal(id);
      }
    });
  });

  document.querySelectorAll('.assignment-card').forEach((card) => {
    card.addEventListener('click', () => {
      const id = card.dataset.assignmentId;
      if (id) openAssignmentModal(id);
    });
    card.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        const id = card.dataset.assignmentId;
        if (id) openAssignmentModal(id);
      }
    });
  });

  if (btnComplete) {
    btnComplete.addEventListener('click', async () => {
      if (!activeScheduledId) return;
      try {
        await postForm(`/lessons/${activeScheduledId}/update/`, { status: 'complete' });
        updateCardBadge(activeScheduledId, 'complete');
        setLessonStatus('complete', 'Complete', 'check-circle-fill', 'success');
      } catch (e) {
        showModalAlert(e.message || 'Failed to mark complete.', 'danger');
      }
    });
  }

  if (btnSkip) {
    btnSkip.addEventListener('click', async () => {
      if (!activeScheduledId) return;
      try {
        await postForm(`/lessons/${activeScheduledId}/update/`, { status: 'skipped' });
        updateCardBadge(activeScheduledId, 'skipped');
        setLessonStatus('skipped', 'Skipped', 'skip-forward-circle', 'dark');
      } catch (e) {
        showModalAlert(e.message || 'Failed to skip lesson.', 'danger');
      }
    });
  }

  if (btnReschedule) {
    btnReschedule.addEventListener('click', async () => {
      if (!activeScheduledId || !rescheduleDate || !rescheduleDate.value) return;
      try {
        await postForm(`/lessons/${activeScheduledId}/reschedule/`, {
          new_date: rescheduleDate.value,
        });
        showModalAlert('Lesson rescheduled.', 'success');
        window.location.reload();
      } catch (e) {
        showModalAlert(e.message || 'Failed to reschedule.', 'danger');
      }
    });
  }

  if (btnEdit) {
    btnEdit.addEventListener('click', async () => {
      if (!activeScheduledId || !rescheduleDate || !rescheduleDate.value) return;
      try {
        await postForm(`/lessons/${activeScheduledId}/edit/`, {
          scheduled_date: rescheduleDate.value,
        });
        showModalAlert('Lesson updated.', 'success');
        window.location.reload();
      } catch (e) {
        showModalAlert(e.message || 'Failed to edit lesson.', 'danger');
      }
    });
  }

  if (btnDelete) {
    btnDelete.addEventListener('click', async () => {
      if (!activeScheduledId) return;
      if (!window.confirm('Delete this scheduled lesson?')) return;
      try {
        await postForm(`/lessons/${activeScheduledId}/delete/`);
        if (bsModal) bsModal.hide();
        window.location.reload();
      } catch (e) {
        showModalAlert(e.message || 'Failed to delete lesson.', 'danger');
      }
    });
  }

  document.querySelectorAll('.mastery-btn').forEach((btn) => {
    btn.addEventListener('click', async () => {
      if (!activeScheduledId) return;
      const mastery = btn.dataset.mastery;
      try {
        await postForm(`/lessons/${activeScheduledId}/mastery/`, { mastery });
        setActiveMastery(mastery);
        updateCardMastery(activeScheduledId, mastery);
      } catch (e) {
        showModalAlert(e.message || 'Failed to update mastery.', 'danger');
      }
    });
  });

  if (modalNotes && notesCount) {
    modalNotes.addEventListener('input', () => {
      notesCount.textContent = modalNotes.value.length;
    });
  }

  if (btnSaveNotes) {
    btnSaveNotes.addEventListener('click', async () => {
      if (!activeScheduledId || !modalNotes) return;
      try {
        await postForm(`/lessons/${activeScheduledId}/notes/`, { notes: modalNotes.value });
        showModalAlert('Notes saved.', 'success');
      } catch (e) {
        showModalAlert(e.message || 'Failed to save notes.', 'danger');
      }
    });
  }

  if (btnSaveReceipt) {
    btnSaveReceipt.addEventListener('click', async () => {
      if (!activeScheduledId || !receiptInput) return;
      try {
        const data = await postForm(`/lessons/${activeScheduledId}/receipt/`, {
          receipt_url: receiptInput.value,
        });
        renderReceiptPreview(data.completion_receipt_meta || {});
        showModalAlert('Receipt link saved.', 'success');
      } catch (e) {
        showModalAlert(e.message || 'Failed to save receipt link.', 'danger');
      }
    });
  }

  if (btnAddComment) {
    btnAddComment.addEventListener('click', async () => {
      if (!activeScheduledId || !commentInput || !commentInput.value.trim()) return;
      try {
        const data = await postForm(`/lessons/${activeScheduledId}/comments/`, {
          body: commentInput.value,
        });
        commentInput.value = '';
        appendComment(data.comment);
        if (commentsCountTab) commentsCountTab.textContent = data.comments_count;
      } catch (e) {
        showModalAlert(e.message || 'Failed to add comment.', 'danger');
      }
    });
  }

  document.querySelectorAll('.lesson-tab-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      activateLessonTab(btn.dataset.tab);
    });
  });

  if (btnUpload) {
    btnUpload.addEventListener('click', async () => {
      if (!activeScheduledId || !evidenceFile || !evidenceFile.files.length) {
        showModalAlert('Please choose a file first.', 'warning');
        return;
      }

      const formData = new FormData();
      formData.append('file', evidenceFile.files[0]);
      btnUpload.disabled = true;
      btnUpload.textContent = 'Uploading...';
      try {
        const resp = await fetch(`/lessons/${activeScheduledId}/upload/`, {
          method: 'POST',
          headers: {
            'X-CSRFToken': getCookie('csrftoken'),
            'X-Requested-With': 'XMLHttpRequest',
          },
          credentials: 'same-origin',
          body: formData,
        });
        const data = await resp.json();
        if (!resp.ok || !data.success) throw new Error(data.error || 'Upload failed.');

        if (evidenceCount) evidenceCount.textContent = data.evidence_count;
        if (submissionsCountTab) submissionsCountTab.textContent = data.evidence_count;
        evidenceFile.value = '';
        const li = document.createElement('li');
        li.dataset.fileId = data.file_id;
        li.className = 'd-flex justify-content-between align-items-center py-1';
        li.innerHTML = `<span class="text-truncate me-2">${data.filename} <span class="text-muted">(${data.uploaded_at})</span></span>
          <button class="btn btn-sm btn-outline-danger btn-delete-evidence py-0 px-1" data-fid="${data.file_id}" type="button">&times;</button>`;
        if (evidenceList) evidenceList.appendChild(li);
        showModalAlert('Submission uploaded successfully.', 'success');
      } catch (e) {
        showModalAlert(e.message || 'Upload failed.', 'danger');
      } finally {
        btnUpload.disabled = false;
        btnUpload.textContent = 'Upload';
      }
    });
  }

  if (evidenceList) {
    evidenceList.addEventListener('click', async (e) => {
      const btn = e.target.closest('.btn-delete-evidence');
      if (!btn) return;
      if (!window.confirm('Delete this submission?')) return;
      const fid = btn.dataset.fid;
      try {
        const resp = await fetch(`/evidence/${fid}/delete/`, {
          method: 'POST',
          headers: {
            'X-CSRFToken': getCookie('csrftoken'),
            'X-Requested-With': 'XMLHttpRequest',
          },
          credentials: 'same-origin',
        });
        const data = await resp.json();
        if (!resp.ok || !data.success) throw new Error(data.error || 'Delete failed.');

        const li = evidenceList.querySelector(`[data-file-id="${fid}"]`);
        if (li) li.remove();
        if (evidenceCount) evidenceCount.textContent = data.evidence_count;
        if (submissionsCountTab) submissionsCountTab.textContent = data.evidence_count;
        showModalAlert('Submission deleted.', 'success');
      } catch (err) {
        showModalAlert(err.message || 'Delete failed.', 'danger');
      }
    });
  }

  async function postAssignmentStatusUpdate(assignmentId, status) {
    const body = new URLSearchParams({ status });
    const resp = await fetch(`/assignments/${assignmentId}/update/`, {
      method: 'POST',
      headers: {
        'X-CSRFToken': getCookie('csrftoken'),
        'X-Requested-With': 'XMLHttpRequest',
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      credentials: 'same-origin',
      body,
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return resp.json();
  }

  function updateAssignmentBadge(assignmentId, status) {
    const card = document.querySelector(`.assignment-card[data-assignment-id="${assignmentId}"]`);
    if (!card) return;
    const labelMap = { done: 'Done', incomplete: 'Incomplete', overdue: 'Overdue' };
    const classMap = { done: 'bg-success', incomplete: 'text-bg-secondary', overdue: 'bg-danger' };
    card.classList.remove('assignment-done', 'assignment-incomplete', 'assignment-overdue');
    card.classList.add(`assignment-${status}`);
    card.dataset.assignmentStatus = status;
    const badge = card.querySelector('.badge');
    if (badge) {
      badge.className = `badge ${classMap[status] || 'text-bg-secondary'}`;
      badge.textContent = labelMap[status] || 'Incomplete';
    }
  }

  if (assignmentBtnDone) {
    assignmentBtnDone.addEventListener('click', async () => {
      if (!activeAssignmentId) return;
      try {
        const data = await postAssignmentStatusUpdate(activeAssignmentId, 'done');
        if (data.success) updateAssignmentBadge(activeAssignmentId, data.status);
      } catch (e) {
        // silent
      }
      if (assignmentModal) assignmentModal.hide();
    });
  }

  if (assignmentBtnIncomplete) {
    assignmentBtnIncomplete.addEventListener('click', async () => {
      if (!activeAssignmentId) return;
      try {
        const data = await postAssignmentStatusUpdate(activeAssignmentId, 'incomplete');
        if (data.success) updateAssignmentBadge(activeAssignmentId, data.status);
      } catch (e) {
        // silent
      }
      if (assignmentModal) assignmentModal.hide();
    });
  }
})();
