/* EduTrack — Calendar lesson card click → modal population (S2.4)
   + AJAX Complete / Skip status update (S2.5)
   + AJAX Mastery score update with active-state buttons (S2.6)
   + AJAX Student Notes save with char counter (S2.7) */

(function () {
  'use strict';

  const modal      = document.getElementById('lesson-modal');
  const bsModal    = modal ? new bootstrap.Modal(modal) : null;
  const modalTitle = document.getElementById('modal-title');
  const modalHdr   = document.getElementById('modal-header');
  const modalSubj  = document.getElementById('modal-subject');
  const modalDate  = document.getElementById('modal-date');
  const modalUnit  = document.getElementById('modal-unit');
  const modalOak   = document.getElementById('modal-oak-link');
  const modalStatus = document.getElementById('modal-status-text');
  const modalNotes  = document.getElementById('modal-notes');
  const notesCount  = document.getElementById('notes-char-count');
  const btnSaveNotes = document.getElementById('modal-btn-save-notes');
  const evidenceCount = document.getElementById('modal-evidence-count');
  const evidenceList  = document.getElementById('modal-evidence-list');

  let activeScheduledId = null;

  // ── Modal alert helper ─────────────────────────────────────────────────
  function showModalAlert(message, type) {
    const existing = document.getElementById('modal-upload-alert');
    if (existing) existing.remove();
    const div = document.createElement('div');
    div.id = 'modal-upload-alert';
    div.className = `alert alert-${type} alert-dismissible py-1 px-2 mt-2 mb-0 small`;
    div.innerHTML = `${message}<button type="button" class="btn-close py-2" data-bs-dismiss="alert"></button>`;
    const uploadSection = document.getElementById('modal-evidence-file');
    if (uploadSection) uploadSection.closest('div').after(div);
  }

  // ── CSRF helper ──────────────────────────────────────────────────────────
  function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
    return null;
  }

  // ── Update card badge in the calendar grid ───────────────────────────────
  function updateCardBadge(scheduledId, status) {
    const card = document.querySelector(`.lesson-card[data-id="${scheduledId}"]`);
    if (!card) return;
    const footer = card.querySelector('.card-footer');
    if (!footer) return;

    const labelMap = { complete: 'Complete', skipped: 'Skipped', pending: 'Pending' };
    const classMap = { complete: 'bg-success', skipped: 'bg-secondary', pending: 'bg-light text-dark' };
    const label   = labelMap[status] || status;
    const cls     = classMap[status] || 'bg-light text-dark';

    // Replace the status badge while preserving any mastery dots that follow
    const existingBadge = footer.querySelector('.status-badge');
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

  // ── Render evidence file list in modal ────────────────────────────────────
  function renderEvidenceList(files) {
    if (!evidenceList) return;
    evidenceList.innerHTML = '';
    files.forEach(f => {
      const li = document.createElement('li');
      li.dataset.fileId = f.id;
      li.className = 'd-flex justify-content-between align-items-center py-1';
      li.innerHTML = `<span class="text-truncate me-2">${f.filename} <span class="text-muted">(${f.uploaded_at})</span></span>
        <button class="btn btn-sm btn-outline-danger btn-delete-evidence py-0 px-1" data-fid="${f.id}">&times;</button>`;
      evidenceList.appendChild(li);
    });
  }

  // ── Post notes save ─────────────────────────────────────────────────────
  async function postNotesUpdate(scheduledId, notes) {
    const body = new URLSearchParams({ notes });
    const resp = await fetch(`/lessons/${scheduledId}/notes/`, {
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

  // ── Post mastery update ──────────────────────────────────────────────────
  async function postMasteryUpdate(scheduledId, mastery) {
    const body = new URLSearchParams({ mastery });
    const resp = await fetch(`/lessons/${scheduledId}/mastery/`, {
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

  // ── Set active mastery button state ─────────────────────────────────────
  function setActiveMastery(mastery) {
    document.querySelectorAll('.mastery-btn').forEach(btn => {
      btn.classList.toggle('mastery-active', btn.dataset.mastery === mastery);
    });
  }

  // ── Update card mastery dot in the calendar grid ─────────────────────────
  function updateCardMastery(scheduledId, mastery) {
    const card = document.querySelector(`.lesson-card[data-id="${scheduledId}"]`);
    if (!card) return;
    const footer = card.querySelector('.card-footer');
    if (!footer) return;

    const existing = footer.querySelector('.mastery-dot');
    if (existing) existing.remove();

    if (mastery && mastery !== 'unset') {
      const titleMap = { green: 'Mastery: green', amber: 'Mastery: amber', red: 'Mastery: needs work' };
      const dot = document.createElement('span');
      dot.className = `mastery-dot ${mastery}`;
      dot.title = titleMap[mastery] || '';
      footer.appendChild(dot);
    }
  }

  // ── Post status update ───────────────────────────────────────────────────
  async function postStatusUpdate(scheduledId, status) {
    const body = new URLSearchParams({ status });
    const resp = await fetch(`/lessons/${scheduledId}/update/`, {
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

  // ── Fetch lesson detail and open modal ────────────────────────────────────
  async function openLessonModal(scheduledId) {
    activeScheduledId = scheduledId;
    try {
      const resp = await fetch(`/lessons/${scheduledId}/detail/`, {
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        credentials: 'same-origin',
      });
      if (!resp.ok) return;
      const data = await resp.json();

      // Populate header
      modalTitle.textContent = data.lesson_title;
      modalHdr.style.setProperty('--modal-colour', data.colour_hex);

      // Populate body
      modalSubj.textContent = data.subject_name;
      modalDate.textContent = data.scheduled_date;
      modalUnit.textContent = data.unit_title ? `Unit: ${data.unit_title}` : '';
      modalOak.href = data.lesson_url || '#';

      // Status text
      const statusMap = { pending: 'Pending', complete: 'Complete', skipped: 'Skipped' };
      modalStatus.textContent = `Status: ${statusMap[data.status] || data.status}`;

      // Enable action buttons
      document.querySelectorAll('#modal-btn-complete, #modal-btn-skip, .mastery-btn')
              .forEach(btn => btn.removeAttribute('disabled'));

      // Set active mastery button
      setActiveMastery(data.mastery);

      // Populate notes textarea
      if (modalNotes) {
        modalNotes.value = data.student_notes || '';
        modalNotes.removeAttribute('disabled');
        if (notesCount) notesCount.textContent = (data.student_notes || '').length;
      }
      if (btnSaveNotes) btnSaveNotes.removeAttribute('disabled');
      if (rescheduleDate) rescheduleDate.removeAttribute('disabled');
      if (btnReschedule)  btnReschedule.removeAttribute('disabled');
      if (evidenceFile)   evidenceFile.removeAttribute('disabled');
      if (btnUpload)      btnUpload.removeAttribute('disabled');

      // Update evidence count
      if (evidenceCount) evidenceCount.textContent = data.evidence_count ?? 0;
      renderEvidenceList(data.evidence_files || []);

      bsModal.show();
    } catch (e) {
      // Silent fail — user can reload if needed
    }
  }

  // ── Complete / Skip button handlers ──────────────────────────────────────
  function attachActionButtons() {
    const btnComplete = document.getElementById('modal-btn-complete');
    const btnSkip     = document.getElementById('modal-btn-skip');

    if (btnComplete) {
      btnComplete.addEventListener('click', async () => {
        if (!activeScheduledId) return;
        try {
          const data = await postStatusUpdate(activeScheduledId, 'complete');
          if (data.success) {
            updateCardBadge(activeScheduledId, data.status);
            modalStatus.textContent = `Status: Complete`;
          }
        } catch (e) { /* silent */ }
        bsModal.hide();
      });
    }

    if (btnSkip) {
      btnSkip.addEventListener('click', async () => {
        if (!activeScheduledId) return;
        try {
          const data = await postStatusUpdate(activeScheduledId, 'skipped');
          if (data.success) {
            updateCardBadge(activeScheduledId, data.status);
            modalStatus.textContent = `Status: Skipped`;
          }
        } catch (e) { /* silent */ }
        bsModal.hide();
      });
    }
  }

  // ── Attach click listeners to all lesson cards ───────────────────────────
  document.querySelectorAll('.lesson-card').forEach(card => {
    card.addEventListener('click', () => {
      const id = card.dataset.id;
      if (id) openLessonModal(id);
    });
    // Keyboard accessibility: Enter/Space opens modal
    card.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        const id = card.dataset.id;
        if (id) openLessonModal(id);
      }
    });
  });

  attachActionButtons();

  // ── Mastery button handlers ───────────────────────────────────────────────
  document.querySelectorAll('.mastery-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      if (!activeScheduledId) return;
      const mastery = btn.dataset.mastery;
      try {
        const data = await postMasteryUpdate(activeScheduledId, mastery);
        if (data.success) {
          setActiveMastery(mastery);
          updateCardMastery(activeScheduledId, mastery);
        }
      } catch (e) { /* silent */ }
    });
  });

  // ── Notes char counter ─────────────────────────────────────────────────
  if (modalNotes && notesCount) {
    modalNotes.addEventListener('input', () => {
      notesCount.textContent = modalNotes.value.length;
    });
  }

  // ── Save notes button handler ────────────────────────────────────────────
  if (btnSaveNotes) {
    btnSaveNotes.addEventListener('click', async () => {
      if (!activeScheduledId || !modalNotes) return;
      try {
        await postNotesUpdate(activeScheduledId, modalNotes.value);
      } catch (e) { /* silent */ }
      bsModal.hide();
    });
  }

  // ── Reschedule handler ────────────────────────────────────────────────
  const rescheduleDate = document.getElementById('modal-reschedule-date');
  const btnReschedule  = document.getElementById('modal-btn-reschedule');

  // Set min date to tomorrow when the modal opens
  if (modal) {
    modal.addEventListener('show.bs.modal', () => {
      const tomorrow = new Date();
      tomorrow.setDate(tomorrow.getDate() + 1);
      if (rescheduleDate) rescheduleDate.min = tomorrow.toISOString().slice(0, 10);
    });
  }

  if (btnReschedule) {
    btnReschedule.addEventListener('click', async () => {
      if (!activeScheduledId || !rescheduleDate || !rescheduleDate.value) return;
      try {
        const body = new URLSearchParams({ new_date: rescheduleDate.value });
        const resp = await fetch(`/lessons/${activeScheduledId}/reschedule/`, {
          method: 'POST',
          headers: {
            'X-CSRFToken': getCookie('csrftoken'),
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/x-www-form-urlencoded',
          },
          credentials: 'same-origin',
          body,
        });
        if (resp.ok) {
          bsModal.hide();
          window.location.reload();
        }
      } catch (e) { /* silent */ }
    });
  }

  // ── Evidence upload handler ───────────────────────────────────────────────
  const evidenceFile = document.getElementById('modal-evidence-file');
  const btnUpload    = document.getElementById('modal-btn-upload');

  if (btnUpload) {
    btnUpload.addEventListener('click', async () => {
      if (!activeScheduledId || !evidenceFile || !evidenceFile.files.length) {
        showModalAlert('Please choose a file first.', 'warning');
        return;
      }
      const formData = new FormData();
      formData.append('file', evidenceFile.files[0]);
      btnUpload.disabled = true;
      btnUpload.textContent = 'Uploading…';
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
        if (resp.ok && data.success) {
          if (evidenceCount) evidenceCount.textContent = data.evidence_count;
          evidenceFile.value = '';
          if (evidenceList) {
            const li = document.createElement('li');
            li.dataset.fileId = data.file_id;
            li.className = 'd-flex justify-content-between align-items-center py-1';
            li.innerHTML = `<span class="text-truncate me-2">${data.filename} <span class="text-muted">(${data.uploaded_at})</span></span>
              <button class="btn btn-sm btn-outline-danger btn-delete-evidence py-0 px-1" data-fid="${data.file_id}">&times;</button>`;
            evidenceList.appendChild(li);
          }
          showModalAlert('File uploaded successfully.', 'success');
        } else {
          showModalAlert(data.error || 'Upload failed. Please try again.', 'danger');
        }
      } catch (e) {
        showModalAlert('Upload failed: network error.', 'danger');
      } finally {
        btnUpload.disabled = false;
        btnUpload.textContent = 'Upload';
      }
    });
  }
  // ── Evidence delete handler ────────────────────────────────────────────
  if (evidenceList) {
    evidenceList.addEventListener('click', async (e) => {
      const btn = e.target.closest('.btn-delete-evidence');
      if (!btn) return;
      if (!confirm('Delete this evidence file?')) return;
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
        if (resp.ok) {
          const data = await resp.json();
          if (data.success) {
            const li = evidenceList.querySelector(`[data-file-id="${fid}"]`);
            if (li) li.remove();
            if (evidenceCount) evidenceCount.textContent = data.evidence_count;
          }
        }
      } catch (e) { /* silent */ }
    });
  }
})();
