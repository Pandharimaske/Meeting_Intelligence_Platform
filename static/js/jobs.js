/* ── jobs.js — job list, polling, job switching ──────────────────── */

const Jobs = (() => {

  const STATUS_STEPS = ['transcribing', 'chunking', 'indexing', 'generating_mom', 'completed'];

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

      /* video */
      Video.load(job.source_video ? Api.videoUrl(jobId) : null);

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

      /* Clips */
      Clips.init(jobId, !!job.source_video);

    } catch (err) {
      console.error('loadAndRender error', err);
    }
  }

  /* ── Polling ──────────────────────────────────────────────────── */
  function startPolling(jobId) {
    State.stopPoll();
    let attempts = 0;
    const interval = setInterval(async () => {
      attempts++;
      try {
        const job = await Api.job(jobId);
        UI.updatePipeline(job.status);
        _upsertCard(job);

        const pct = _progressPct(job.status);
        UI.setProgress(pct);

        if (job.status === 'completed') {
          clearInterval(interval);
          await loadAndRender(jobId);
          UI.hideOverlay();
          UI.toast('Processing complete! ✨', 'success');
        } else if (job.status === 'failed') {
          clearInterval(interval);
          UI.hideOverlay();
          UI.toast(`Failed: ${job.error || 'unknown error'}`, 'error');
        }
      } catch (e) { console.error('poll error', e); }

      if (attempts > 200) clearInterval(interval);
    }, 2500);

    State.set('pollInterval', interval);
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
    return `
      <div data-job-id="${id}" class="job-card ${id === current ? 'active' : ''}">
        <div class="job-name" title="${name}">${name}</div>
        <div class="job-meta">
          <span class="job-dot ${dotCls}"></span>
          <span>${label}</span>
          ${job.duration_seconds ? `<span>· ${UI.formatTime(job.duration_seconds)}</span>` : ''}
        </div>
      </div>`;
  }

  function _markActive(jobId) {
    document.querySelectorAll('.job-card').forEach(c => {
      c.classList.toggle('active', c.dataset.jobId === jobId);
    });
  }

  return { loadAll, loadAndRender, startPolling };
})();
