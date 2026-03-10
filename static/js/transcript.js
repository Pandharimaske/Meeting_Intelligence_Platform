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
      const start   = seg.start ?? 0;
      const end     = seg.end   ?? 0;
      const ts      = start != null ? UI.formatTime(start) : '';
      const hasClip = (end - start) > 1; // only offer clip if segment > 1s

      return `
        <div class="transcript-entry fade-up">
          <div class="t-left">
            ${ts ? `
              <span class="t-timestamp"
                    onclick="Video.seekTo('${ts}')"
                    title="Seek to ${ts}">${ts}</span>` : ''}
            ${hasClip ? `
              <button class="t-clip-btn"
                      onclick="Clips.playClip(${start}, ${end}, '${_esc(speaker)} @ ${ts}')"
                      title="Play clip for this segment">
                <i class="fas fa-scissors"></i>
              </button>` : ''}
          </div>
          <span class="t-speaker-badge ${cls}">${_esc(speaker)}</span>
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

  function _esc(str) {
    return String(str).replace(/'/g, "\\'").replace(/"/g, '&quot;');
  }

  return { render, setPlaceholder };
})();
