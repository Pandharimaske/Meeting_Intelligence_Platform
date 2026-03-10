/* ── transcript.js — transcript tab rendering ────────────────────── */

const Transcript = (() => {

  function render(transcript) {
    const el   = document.getElementById('tab-transcript');
    const segs = (transcript.speaker_segments?.length
      ? transcript.speaker_segments
      : transcript.segments) || [];

    if (!segs.length) {
      el.innerHTML = `<p class="t-text" style="padding:30px 0">${transcript.text || 'No segments available.'}</p>`;
      return;
    }

    el.innerHTML = segs.map(seg => {
      const speaker = seg.speaker || 'Unknown';
      const cls     = State.getSpeakerClass(speaker);
      const ts      = seg.start != null ? UI.formatTime(seg.start) : '';
      return `
        <div class="transcript-entry fade-up">
          ${ts ? `<span class="t-timestamp">${ts}</span>` : ''}
          <span class="t-speaker-badge ${cls}">${speaker}</span>
          <span class="t-text">${_escape(seg.text || '')}</span>
        </div>`;
    }).join('');
  }

  function setPlaceholder() {
    document.getElementById('tab-transcript').innerHTML =
      UI.placeholder('fa-spinner fa-spin', 'Transcript will appear here once processing is complete.');
  }

  function _escape(str) {
    return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  return { render, setPlaceholder };
})();
