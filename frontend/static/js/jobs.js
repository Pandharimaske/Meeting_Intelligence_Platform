/* ── jobs.js — job list, polling, job switching ──────────────────── */

const Jobs = (() => {

  /* ── Initial load ─────────────────────────────────────────────── */
  async function loadAll() {
    try {
      const { jobs = [] } = await Api.jobs();
      const list = document.getElementById('jobsList');
      if (!jobs.length) {
        list.innerHTML = `<div class="jobs-empty"><i class="fas fa-inbox"></i>No meetings yet</div>`;
        return;
      }
      list.innerHTML = '';
      jobs.forEach(job => _upsertCard(job));
    } catch (err) {
      console.error('loadAll jobs error', err);
    }
  }

  /* ── Load + render a single job ───────────────────────────────── */
  async function loadAndRender(jobId) {
    try {
      const job = await Api.job(jobId);
      State.set('currentJobId', jobId);

      UI.showJobView();
      UI.updatePipeline(job.status);
      _upsertCard(job);
      _markActive(jobId);

      /* video — source_video is a URL string when present */
      const hasVideo = !!(job.source_video);
      Video.load(hasVideo ? Api.videoUrl(jobId) : null);

      /* transcript */
      if (job.transcript_available && job.transcript) {
        Transcript.render(job.transcript);
      } else {
        Transcript.setPlaceholder();
      }

      /* MoM */
      if (job.mom_available && job.mom && Object.keys(job.mom).length) {
        MoM.render(job.mom);
      } else {
        MoM.setPlaceholder(job.status);
      }

      /* Clips — pass correct boolean */
      Clips.init(jobId, hasVideo);

    } catch (err) {
      console.error('loadAndRender error', err);
    }
  }

  /* ── Real-time updates via WebSocket ─────────────────────────── */
  function startPolling(jobId) {
    // Use WebSocket for real-time updates instead of polling
    WebSocketManager.connect(jobId);
  }

  /* ── Internal helpers ─────────────────────────────────────────── */
  function _progressPct(status) {
    const map = { uploaded: 10, transcribing: 25, chunking: 48, indexing: 65, generating_mom: 82, completed: 100 };
    return map[status] || 10;
  }

  function _upsertCard(job) {
    const list    = document.getElementById('jobsList');
    const id      = job.job_id || job.id;
    const isEmpty = list.querySelector('.jobs-empty');
    if (isEmpty) list.innerHTML = '';

    const existing = list.querySelector(`[data-job-id="${id}"]`);
    const card     = _buildCard(job);

    if (existing) existing.outerHTML = card;
    else list.insertAdjacentHTML('afterbegin', card);

    list.querySelector(`[data-job-id="${id}"]`)
        .addEventListener('click', () => {
          State.set('currentJobId', id);
          State.clearChat();
          Chat.resetUI();
          loadAndRender(id);
        });
  }

  function _buildCard(job) {
    const id      = job.job_id || job.id;
    const current = State.get('currentJobId');
    const dotCls  = job.status === 'completed' ? 'completed'
                  : job.status === 'failed'    ? 'failed'
                  : 'processing';
    const name    = job.filename || 'Meeting';
    const label   = job.status.replace(/_/g, ' ');
    const icon    = job.file_type === 'video' ? 'fa-film'
                  : job.file_type === 'audio' ? 'fa-microphone'
                  : 'fa-file-lines';
    return `
      <div data-job-id="${id}" class="job-card ${id === current ? 'active' : ''}">
        <div class="job-card-icon"><i class="fas ${icon}"></i></div>
        <div class="job-card-content">
          <div class="job-name" title="${name}">${name}</div>
          <div class="job-meta">
            <span class="job-dot ${dotCls}"></span>
            <span>${label}</span>
            ${job.duration_seconds ? `<span>· ${UI.formatTime(job.duration_seconds)}</span>` : ''}
          </div>
        </div>
      </div>`;
  }

  function _markActive(jobId) {
    document.querySelectorAll('.job-card').forEach(c => {
      c.classList.toggle('active', c.dataset.jobId === jobId);
    });
  }

  /* ── Update job card from WebSocket ───────────────────────────── */
  function updateJobCard(jobId, updates) {
    const card = document.querySelector(`[data-job-id="${jobId}"]`);
    if (!card) return;

    // Update status
    if (updates.status) {
      card.className = `job-card status-${updates.status}`;
      const statusEl = card.querySelector('.job-status');
      if (statusEl) statusEl.textContent = updates.status;
    }

    // Update step
    if (updates.step) {
      const stepEl = card.querySelector('.job-step');
      if (stepEl) stepEl.textContent = updates.step;
    }

    // Update progress
    if (updates.progress !== undefined) {
      const progressEl = card.querySelector('.job-progress');
      if (progressEl) progressEl.style.width = `${updates.progress}%`;
    }
  }

  return { loadAll, loadAndRender, startPolling, updateJobCard };
})();
