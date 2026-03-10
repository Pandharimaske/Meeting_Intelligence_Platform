/* ── transcript.js — transcript tab rendering ────────────────────── */

const Transcript = (() => {

  function render(transcript) {
    const el   = document.getElementById('tab-transcript');
    const segs = (transcript.speaker_segments?.length
      ? transcript.speaker_segments
      : transcript.segments) || [];

    if (!segs.length) {
      el.innerHTML = `<p class="t-text" style="padding:30px 0">${_escHtml(transcript.text || 'No segments available.')}</p>`;
      return;
    }

    // Build speaker stats for the summary bar
    const speakerTimes = {};
    segs.forEach(seg => {
      const sp = seg.speaker || 'Unknown';
      speakerTimes[sp] = (speakerTimes[sp] || 0) + ((seg.end || 0) - (seg.start || 0));
    });
    const totalTime = Object.values(speakerTimes).reduce((a, b) => a + b, 0) || 1;

    // Speaker legend
    const speakerNames = Object.keys(speakerTimes);
    const legendHtml = speakerNames.length > 1 ? `
      <div class="transcript-legend">
        ${speakerNames.map(sp => {
          const cls = State.getSpeakerClass(sp);
          const pct = Math.round((speakerTimes[sp] / totalTime) * 100);
          return `<div class="legend-item">
            <span class="legend-dot ${cls}"></span>
            <span class="legend-name">${_escHtml(sp)}</span>
            <span class="legend-pct">${pct}%</span>
          </div>`;
        }).join('')}
      </div>` : '';

    el.innerHTML = legendHtml + segs.map((seg, idx) => {
      const speaker = seg.speaker || 'Unknown';
      const cls     = State.getSpeakerClass(speaker);
      const start   = seg.start ?? 0;
      const end     = seg.end   ?? 0;
      const ts      = start != null ? UI.formatTime(start) : '';
      const hasClip = (end - start) > 1;
      // safe label for inline onclick (no quotes or backslashes)
      const clipLabel = `${speaker} @ ${ts}`;

      return `
        <div class="transcript-entry fade-up" style="animation-delay:${Math.min(idx * 15, 300)}ms">
          <div class="t-left">
            ${ts ? `
              <span class="t-timestamp"
                    onclick="Video.seekTo('${_escAttr(ts)}')"
                    title="Seek to ${_escAttr(ts)}">${ts}</span>` : ''}
            ${hasClip ? `
              <button class="t-clip-btn"
                      onclick="Clips.playClip(${start}, ${end}, '${_escAttr(clipLabel)}')"
                      title="Play clip for this segment">
                <i class="fas fa-scissors"></i>
              </button>` : ''}
          </div>
          <span class="t-speaker-badge ${cls}">${_escHtml(speaker)}</span>
          <span class="t-text">${_escHtml(seg.text || '')}</span>
        </div>`;
    }).join('');
  }

  function setPlaceholder() {
    document.getElementById('tab-transcript').innerHTML =
      UI.placeholder('fa-spinner fa-spin', 'Transcript will appear here once processing is complete.');
  }

  /* HTML-escape for text content */
  function _escHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  /* Attribute-safe escape for onclick string args (single-quoted JS strings) */
  function _escAttr(str) {
    return String(str)
      .replace(/\\/g, '\\\\')
      .replace(/'/g, "\\'")
      .replace(/"/g, '&quot;')
      .replace(/\n/g, ' ');
  }

  return { render, setPlaceholder };
})();
