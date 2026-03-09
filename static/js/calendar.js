/* EduTrack — Calendar lesson card click → modal population (S2.4) */

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

      // Enable action buttons (placeholders; wired in S2.5)
      document.querySelectorAll('#modal-btn-complete, #modal-btn-skip, .mastery-btn')
              .forEach(btn => btn.removeAttribute('disabled'));

      bsModal.show();
    } catch (e) {
      // Silent fail — user can reload if needed
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
})();
