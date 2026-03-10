/* ── upload.js — file selection & upload flow ────────────────────── */

const Upload = (() => {

  function init() {
    const zone   = document.getElementById('uploadZone');
    const input  = document.getElementById('fileInput');
    const btn    = document.getElementById('uploadBtn');
    const nameEl = document.getElementById('uploadFileName');

    /* click zone → open picker */
    zone.addEventListener('click', () => input.click());

    /* file selected */
    input.addEventListener('change', e => {
      const file = e.target.files[0];
      if (file) _onFileChosen(file, nameEl, btn);
    });

    /* drag-and-drop */
    zone.addEventListener('dragover',  e => { e.preventDefault(); zone.classList.add('drag-over'); });
    zone.addEventListener('dragleave', ()  => zone.classList.remove('drag-over'));
    zone.addEventListener('drop', e => {
      e.preventDefault();
      zone.classList.remove('drag-over');
      const file = e.dataTransfer.files[0];
      if (file) { input.files = e.dataTransfer.files; _onFileChosen(file, nameEl, btn); }
    });

    /* upload button */
    btn.addEventListener('click', _handleUpload);
  }

  function _onFileChosen(file, nameEl, btn) {
    State.set('selectedFile', file);
    nameEl.textContent = file.name;
    nameEl.style.display = 'block';
    btn.disabled = false;
  }

  async function _handleUpload() {
    const file = State.get('selectedFile');
    if (!file) return;

    document.getElementById('uploadBtn').disabled = true;

    UI.showOverlay('Uploading…', 'Sending your file to the server');
    UI.setProgress(8);

    try {
      const result = await Api.upload(file);
      State.set('currentJobId', result.job_id);
      State.clearChat();
      State.resetSpeakers();

      UI.showOverlay('Processing…', 'Transcribing and analysing your meeting');
      UI.setProgress(15);
      UI.showJobView();

      Jobs.startPolling(result.job_id);
      Jobs.loadAndRender(result.job_id);

      UI.toast('Uploaded! Processing has started.', 'success');
    } catch (err) {
      console.error(err);
      UI.toast('Upload failed — check the console.', 'error');
      UI.hideOverlay();
      document.getElementById('uploadBtn').disabled = false;
    }
  }

  return { init };
})();
