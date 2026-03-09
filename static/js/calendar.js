/* EduTrack — Calendar lesson card click → modal population (S2.4)
   + AJAX Complete / Skip status update (S2.5) */

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

  let activeScheduledId = null;

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
})();
