/* ── clips.js — clip retrieval, generation, and inline playback ── */

const Clips = (() => {

  let _jobId   = null;
  let _hasVideo = false;

  /* ── Init ─────────────────────────────────────────────────────── */
  function init(jobId, hasVideo) {
    _jobId    = jobId;
    _hasVideo = hasVideo;
  }

  /* ── Request + play a clip ────────────────────────────────────── */
  async function playClip(start, end, label) {
    if (!_jobId) { UI.toast('No job selected.', 'error'); return; }
    if (!_hasVideo) {
      UI.toast('No video available for this meeting.', 'info');
      return;
    }

    _showClipPanel();
    _setClipLoading(label || `${_fmtSecs(start)} – ${_fmtSecs(end)}`);

    try {
      const data = await Api.clip(_jobId, start, end);
      if (data.clip_url) {
        _renderClipPlayer(data.clip_url, start, end, label);
      } else {
        _setClipError('Clip generation failed.');
      }
    } catch (err) {
      console.error('clip error', err);
      _setClipError('Could not generate clip. Is the video file available?');
    }
  }

  /* ── Seek main player to timestamp and flash it ──────────────── */
  function seekMain(start) {
    Video.seekTo(_fmtSecs(start));
    // Switch to the video tab area (scroll into view on mobile)
    document.getElementById('videoWrapper')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  /* ── Panel helpers ────────────────────────────────────────────── */
  function _showClipPanel() {
    const panel = document.getElementById('clipPanel');
    if (panel) panel.classList.remove('hidden');
  }

  function hideClipPanel() {
    const panel = document.getElementById('clipPanel');
    if (panel) panel.classList.add('hidden');
    // Stop any playing clip
    const v = document.getElementById('clipVideo');
    if (v) { v.pause(); v.src = ''; }
  }

  function _setClipLoading(label) {
    const body = document.getElementById('clipPanelBody');
    if (!body) return;
    body.innerHTML = `
      <div class="clip-loading">
        <i class="fas fa-spinner fa-spin"></i>
        <span>Generating clip: <strong>${_esc(label)}</strong></span>
      </div>`;
  }

  function _setClipError(msg) {
    const body = document.getElementById('clipPanelBody');
    if (!body) return;
    body.innerHTML = `
      <div class="clip-error">
        <i class="fas fa-circle-exclamation"></i>
        <span>${_esc(msg)}</span>
      </div>`;
  }

  function _renderClipPlayer(clipUrl, start, end, label) {
    const body = document.getElementById('clipPanelBody');
    if (!body) return;
    const fullUrl = clipUrl.startsWith('http') ? clipUrl : `http://localhost:8000${clipUrl}`;
    body.innerHTML = `
      <div class="clip-label">
        <i class="fas fa-scissors"></i>
        <span>${_esc(label || `${_fmtSecs(start)} – ${_fmtSecs(end)}`)}</span>
      </div>
      <video
        id="clipVideo"
        controls
        autoplay
        style="width:100%;border-radius:8px;background:#000;display:block;"
      >
        <source src="${fullUrl}" type="video/mp4" />
        Your browser does not support the video tag.
      </video>
      <div class="clip-actions">
        <button class="clip-action-btn" onclick="Video.seekTo('${_fmtSecs(start)}')">
          <i class="fas fa-play-circle"></i> Seek in full video
        </button>
        <a class="clip-action-btn" href="${fullUrl}" download>
          <i class="fas fa-download"></i> Download clip
        </a>
      </div>`;
  }

  /* ── Utilities ────────────────────────────────────────────────── */
  function _fmtSecs(secs) {
    const s = Math.floor(secs || 0);
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    return h > 0
      ? `${h}:${String(m).padStart(2,'0')}:${String(sec).padStart(2,'0')}`
      : `${m}:${String(sec).padStart(2,'0')}`;
  }

  function _esc(str) {
    return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  return { init, playClip, seekMain, hideClipPanel };
})();
