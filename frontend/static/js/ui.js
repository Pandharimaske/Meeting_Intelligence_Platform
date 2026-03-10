/* ── ui.js — shared UI utilities ────────────────────────────────── */

const UI = {

  /* ── Toast notifications ─────────────────────────────────────── */
  toast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    const icons = { success: 'fa-check-circle', error: 'fa-circle-exclamation', info: 'fa-info-circle' };
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.innerHTML = `<i class="fas ${icons[type] || icons.info}"></i> ${message}`;
    container.appendChild(el);
    setTimeout(() => {
      el.style.animation = 'toast-out 0.25s ease forwards';
      setTimeout(() => el.remove(), 250);
    }, 3800);
  },

  /* ── Upload overlay ──────────────────────────────────────────── */
  showOverlay(title = 'Processing…', sub = 'This may take a few minutes') {
    document.getElementById('overlayTitle').textContent = title;
    document.getElementById('overlaySub').textContent   = sub;
    document.getElementById('uploadOverlay').classList.add('visible');
  },

  hideOverlay() {
    document.getElementById('uploadOverlay').classList.remove('visible');
  },

  setProgress(pct) {
    document.getElementById('overlayProgressFill').style.width = `${pct}%`;
  },

  /* ── Show/hide main panels ───────────────────────────────────── */
  showEmpty() {
    document.getElementById('emptyState').classList.remove('hidden');
    document.getElementById('jobView').classList.add('hidden');
  },

  showJobView() {
    document.getElementById('emptyState').classList.add('hidden');
    document.getElementById('jobView').classList.remove('hidden');
  },

  /* ── Tab switching ───────────────────────────────────────────── */
  initTabs() {
    document.querySelectorAll('.tab-btn').forEach(btn => {
      btn.addEventListener('click', () => UI.switchTab(btn.dataset.tab));
    });
  },

  switchTab(tabId) {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tabId));
    document.querySelectorAll('.tab-pane').forEach(p => {
      const isActive = p.id === `tab-${tabId}`;
      p.classList.toggle('active', isActive);
      // Chat pane needs flex; others block — CSS handles this via #tab-chat.active
    });
  },

  /* ── Pipeline progress bar ───────────────────────────────────── */
  updatePipeline(status) {
    const steps = [
      { key: 'upload',        label: 'Upload',       icon: 'fa-upload',   done: true },
      { key: 'transcribe',    label: 'Transcribe',   icon: 'fa-waveform', done: ['transcribing','chunking','indexing','generating_mom','completed'].includes(status) },
      { key: 'chunk',         label: 'Chunk',        icon: 'fa-layer-group', done: ['chunking','indexing','generating_mom','completed'].includes(status) },
      { key: 'embed',         label: 'Embed',        icon: 'fa-vector-square', done: ['indexing','generating_mom','completed'].includes(status) },
      { key: 'mom',           label: 'MoM',          icon: 'fa-file-lines', done: ['generating_mom','completed'].includes(status) },
      { key: 'ready',         label: 'Ready',        icon: 'fa-circle-check', done: status === 'completed' },
    ];

    const isActive = (i) => !steps[i].done && (i === 0 || steps[i - 1].done);

    document.getElementById('pipelineBar').innerHTML = steps.map((s, i) => `
      <div class="pipeline-step ${s.done ? 'done' : ''} ${isActive(i) ? 'active' : ''}">
        <div class="step-node">
          ${s.done ? '<i class="fas fa-check"></i>' : isActive(i) ? '<i class="fas fa-spinner spin"></i>' : i + 1}
        </div>
        <span class="step-label">${s.label}</span>
      </div>`).join('');
  },

  /* ── Placeholder ─────────────────────────────────────────────── */
  placeholder(icon, text) {
    return `<div class="placeholder-text"><i class="fas ${icon}"></i>${text}</div>`;
  },

  /* ── Time formatter ──────────────────────────────────────────── */
  formatTime(seconds) {
    const s = Math.floor(seconds || 0);
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    return h > 0
      ? `${h}:${String(m).padStart(2,'0')}:${String(sec).padStart(2,'0')}`
      : `${m}:${String(sec).padStart(2,'0')}`;
  },
};
