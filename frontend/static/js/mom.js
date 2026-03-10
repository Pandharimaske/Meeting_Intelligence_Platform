/* ── mom.js — Minutes of Meeting tab rendering ───────────────────── */

const MoM = (() => {

  function render(mom) {
    const el = document.getElementById('tab-mom');
    let html = '';

    /* Title */
    if (mom.title) {
      html += `<div class="mom-title">${_esc(mom.title)}</div>`;
    }

    /* Summary */
    if (mom.summary) {
      html += `
        <div class="mom-section">
          <div class="mom-section-header">
            <i class="fas fa-align-left" style="color:var(--accent-light)"></i> Summary
          </div>
          <div class="summary-card">${_esc(mom.summary)}</div>
        </div>`;
    }

    /* Agenda */
    if (mom.agenda?.length) {
      html += `
        <div class="mom-section">
          <div class="mom-section-header">
            <i class="fas fa-list-check" style="color:var(--sky)"></i> Agenda
          </div>
          <div class="agenda-list">
            ${mom.agenda.map((item, i) => `
              <div class="agenda-item fade-up" style="animation-delay:${i * 40}ms">
                <span class="agenda-num">${i + 1}</span>
                <span>${_esc(typeof item === 'string' ? item : JSON.stringify(item))}</span>
              </div>`).join('')}
          </div>
        </div>`;
    }

    /* Key Points */
    if (mom.key_points?.length) {
      html += `
        <div class="mom-section">
          <div class="mom-section-header">
            <i class="fas fa-key" style="color:var(--violet)"></i> Key Points
          </div>
          ${mom.key_points.map((kp, i) => {
            const ts      = kp.timestamp || '';
            const speaker = kp.speaker   || '';
            const point   = kp.point     || (typeof kp === 'string' ? kp : '');
            return `
              <div class="kp-card fade-up" style="animation-delay:${i * 40}ms">
                <div class="kp-meta">
                  ${ts      ? `<span class="kp-ts seekable" onclick="Video.seekTo('${_escAttr(ts)}')" title="Seek to ${_escAttr(ts)}"><i class="fas fa-clock"></i>${ts}</span>` : ''}
                  ${speaker ? `<span class="kp-speaker">${_esc(speaker)}</span>` : ''}
                </div>
                <div class="kp-text">${_esc(point)}</div>
              </div>`;
          }).join('')}
        </div>`;
    }

    /* Decisions */
    if (mom.decisions?.length) {
      html += `
        <div class="mom-section">
          <div class="mom-section-header">
            <i class="fas fa-circle-check" style="color:var(--emerald)"></i> Decisions
          </div>
          ${mom.decisions.map((d, i) => {
            const ts  = d.timestamp || '';
            const dec = d.decision  || (typeof d === 'string' ? d : '');
            return `
              <div class="decision-item fade-up" style="animation-delay:${i * 40}ms">
                ${ts ? `<span class="decision-ts seekable" onclick="Video.seekTo('${_escAttr(ts)}')" title="Seek to ${_escAttr(ts)}"><i class="fas fa-clock"></i>${ts}</span>` : ''}
                <span class="decision-text">${_esc(dec)}</span>
              </div>`;
          }).join('')}
        </div>`;
    }

    /* Action Items */
    if (mom.action_items?.length) {
      html += `
        <div class="mom-section">
          <div class="mom-section-header">
            <i class="fas fa-bolt" style="color:var(--amber)"></i> Action Items
          </div>
          ${mom.action_items.map((a, i) => {
            const ts    = a.timestamp || '';
            const owner = a.owner     || 'Unknown';
            const task  = a.task      || (typeof a === 'string' ? a : '');
            return `
              <div class="action-item fade-up" style="animation-delay:${i * 40}ms">
                <div class="action-meta">
                  ${ts ? `<span class="action-ts seekable" onclick="Video.seekTo('${_escAttr(ts)}')" title="Seek to ${_escAttr(ts)}"><i class="fas fa-clock"></i>${ts}</span>` : ''}
                  <span class="action-owner"><i class="fas fa-user-check"></i>${_esc(owner)}</span>
                </div>
                <div class="action-text">${_esc(task)}</div>
              </div>`;
          }).join('')}
        </div>`;
    }

    el.innerHTML = html || UI.placeholder('fa-file-circle-question', 'No minutes data available.');
  }

  function setPlaceholder(status) {
    const msg = status === 'completed'
      ? 'Minutes not yet generated.'
      : 'Minutes will appear once processing finishes.';
    document.getElementById('tab-mom').innerHTML = UI.placeholder('fa-file-lines', msg);
  }

  /* HTML-escape text content */
  function _esc(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  /* Attribute-safe escape for onclick string args */
  function _escAttr(str) {
    return String(str)
      .replace(/\\/g, '\\\\')
      .replace(/'/g, "\\'")
      .replace(/"/g, '&quot;')
      .replace(/\n/g, ' ');
  }

  return { render, setPlaceholder };
})();
