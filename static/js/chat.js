/* ── chat.js — AI chat tab ───────────────────────────────────────── */

const Chat = (() => {

  let _busy = false;

  function init() {
    document.getElementById('chatInput').addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); _send(); }
    });
    document.getElementById('sendChatBtn').addEventListener('click', _send);
  }

  function resetUI() {
    document.getElementById('chatMessages').innerHTML = _emptyHtml();
    Sources.clear();
  }

  /* ── Send ─────────────────────────────────────────────────────── */
  async function _send() {
    if (_busy) return;
    const jobId = State.get('currentJobId');
    if (!jobId) { UI.toast('No meeting selected.', 'error'); return; }

    const input = document.getElementById('chatInput');
    const text  = input.value.trim();
    if (!text) return;

    _busy = true;
    input.value = '';
    _setBtnState(true);

    _appendBubble('user', text);
    State.pushChat('user', text);

    const typingId = _appendTyping();

    try {
      const res = await Api.chat(jobId, text, State.get('chatHistory').slice(-12));
      _removeTyping(typingId);
      const answer = res.answer || 'No response.';
      _appendBubble('system', answer);
      State.pushChat('assistant', answer);

      if (res.wants_clip) {
        Sources.clear();
        if (res.sources?.length) {
          _appendClipPanel(res.sources, jobId);
        } else {
          UI.toast('No video segments found for your query. Try being more specific.', 'info');
        }
      } else {
        Sources.clear();
      }

    } catch (err) {
      _removeTyping(typingId);
      _appendBubble('system', '⚠ Failed to get a response. Please try again.');
      console.error('chat error', err);
    }

    _busy = false;
    _setBtnState(false);
  }

  /* ── Clip panel: all clips grouped ────────────────────────────── */
  function _appendClipPanel(sources, jobId) {
    const msgs = document.getElementById('chatMessages');

    const header = document.createElement('div');
    header.className = 'clip-panel-header fade-up';
    header.innerHTML = `
      <i class="fas fa-film"></i>
      <span>${sources.length} clip${sources.length > 1 ? 's' : ''} found</span>
      <span class="clip-panel-hint">Choose one to watch</span>`;
    msgs.appendChild(header);

    sources.forEach((s, idx) => {
      const start    = s.start ?? 0;
      const end      = s.end   ?? 0;
      const dur      = Math.round(end - start);
      const label    = `${s.start_timestamp || _fmtSecs(start)} – ${s.end_timestamp || _fmtSecs(end)}`;
      const speaker  = (s.primary_speaker && s.primary_speaker !== 'Unknown') ? s.primary_speaker : null;
      const hasClip  = jobId && dur > 0;
      const matchPct = s.score ? Math.round(s.score * 100) : null;

      const accents = ['--accent', '--emerald', '--amber', '--violet', '--sky', '--rose'];
      const accent  = accents[idx % accents.length];

      const card = document.createElement('div');
      card.className = 'clip-result-card fade-up';
      card.style.setProperty('--card-accent', `var(${accent})`);
      card.style.animationDelay = `${idx * 70}ms`;

      card.innerHTML = `
        <div class="crc-index">${idx + 1}</div>
        <div class="crc-body">
          <div class="crc-meta">
            <span class="crc-time"><i class="fas fa-clock"></i> ${_esc(label)}</span>
            <span class="crc-dur">${dur}s</span>
            ${speaker  ? `<span class="crc-speaker">${_esc(speaker)}</span>` : ''}
            ${matchPct ? `<span class="crc-score">${matchPct}% match</span>` : ''}
          </div>
          <div class="crc-text">${_esc(s.text || '')}</div>
          ${hasClip ? `
          <div class="crc-actions">
            <button class="crc-btn-play"
                    onclick="Clips.playClip(${start}, ${end}, '${_escAttr(label)}')"
                    title="Play clip">
              <i class="fas fa-play"></i> Play Clip
            </button>
            <button class="crc-btn-seek"
                    onclick="Clips.seekMain(${start})"
                    title="Jump to this moment">
              <i class="fas fa-forward"></i> Seek in Video
            </button>
          </div>` : `
          <div class="crc-no-video"><i class="fas fa-info-circle"></i> No video — text only</div>`}
        </div>`;

      msgs.appendChild(card);
    });

    msgs.scrollTop = msgs.scrollHeight;
  }

  /* ── DOM helpers ──────────────────────────────────────────────── */
  function _appendBubble(role, text) {
    const div = document.createElement('div');
    div.className = `chat-row ${role} fade-up`;
    const icon = role === 'user' ? 'fa-user' : 'fa-brain';
    const formattedText = role === 'system' ? _linkify(_formatText(text)) : _esc(text);
    div.innerHTML = `
      <div class="chat-avatar"><i class="fas ${icon}"></i></div>
      <div class="chat-bubble">${formattedText}</div>`;
    const msgs = document.getElementById('chatMessages');
    const empty = msgs.querySelector('.chat-empty');
    if (empty) empty.remove();
    msgs.appendChild(div);
    msgs.scrollTop = msgs.scrollHeight;
  }

  function _formatText(text) {
    let f = _esc(text);

    // Headers
    f = f.replace(/^### (.*?)$/gm, '<h4 class="chat-h4">$1</h4>');
    f = f.replace(/^## (.*?)$/gm,  '<h3 class="chat-h3">$1</h3>');
    f = f.replace(/^# (.*?)$/gm,   '<h2 class="chat-h2">$1</h2>');

    // Bold / italic / code
    f = f.replace(/\*\*(.*?)\*\*/g, '<strong class="highlight-term">$1</strong>');
    f = f.replace(/\*(.*?)\*/g,     '<em class="text-emphasis">$1</em>');
    f = f.replace(/`(.*?)`/g,       '<code class="inline-code">$1</code>');

    // FIX: bullet lists — collect ALL consecutive li's into one ul
    // Step 1: convert bullet lines to <li>
    f = f.replace(/^[ \t]*[•\-\*]\s+(.*?)$/gm, '<li class="chat-list-item">$1</li>');
    // Step 2: wrap consecutive <li> blocks in <ul>
    f = f.replace(/(<li class="chat-list-item">(?:.*?)<\/li>\n?)+/g,
      match => `<ul class="chat-list">${match}</ul>`);

    // FIX: numbered lists — same pattern
    f = f.replace(/^[ \t]*\d+\.\s+(.*?)$/gm, '<li class="chat-list-item chat-numbered">$1</li>');
    f = f.replace(/(<li class="chat-list-item chat-numbered">(?:.*?)<\/li>\n?)+/g,
      match => `<ol class="chat-list">${match}</ol>`);

    // Keyword highlights
    ['decision','decided','action item','assigned to','owner:','deadline',
     'critical','important','urgent','approved','rejected','completed'
    ].forEach(kw => {
      f = f.replace(new RegExp(`(${kw})(?=[\\s\\.,;:!?]|$)`, 'gi'),
                    '<mark class="kw-highlight">$1</mark>');
    });

    // Paragraphs — split on double newlines
    f = f.replace(/\n\n+/g, '</p><p class="chat-para">');
    // Single newlines → <br>
    f = f.replace(/\n/g, '<br>');
    f = '<p class="chat-para">' + f + '</p>';

    return f;
  }

  /* ── Timestamp linkifier ──────────────────────────────────────── */
  function _linkify(html) {
    const TS = '(\\d{1,2}:\\d{2}(?::\\d{2})?)';

    // Range: [HH:MM:SS - HH:MM:SS]  (dash, en-dash, em-dash variants)
    const rangeRe = new RegExp(
      `\\[${TS}\\s*(?:-|–|—|&ndash;|&#8211;|&#8212;)\\s*${TS}\\]`, 'g'
    );
    html = html.replace(rangeRe, (_, t1, t2) => {
      const s1 = _tsToSecs(t1);
      const s2 = _tsToSecs(t2);
      const jobId = State.get('currentJobId');
      return `<span class="ts-range-pill" title="Segment ${t1} – ${t2}">
        <span class="ts-pill-icon"><i class="fas fa-clock"></i></span>
        <span class="ts-pill-label">${t1} – ${t2}</span>
        <button class="ts-pill-seek" onclick="Video.seekTo('${t1}')" title="Seek to ${t1}">
          <i class="fas fa-forward"></i>
        </button>
        ${jobId ? `<button class="ts-pill-clip" onclick="Clips.playClip(${s1},${s2},'${t1} – ${t2}')" title="Play clip">
          <i class="fas fa-play"></i>
        </button>` : ''}
      </span>`;
    });

    // Single timestamp: [HH:MM:SS]
    const singleRe = new RegExp(`\\[${TS}\\]`, 'g');
    html = html.replace(singleRe, (_, ts) =>
      `<span class="ts-single-pill" onclick="Video.seekTo('${ts}')" title="Seek to ${ts}">
        <i class="fas fa-clock"></i> ${ts}
      </span>`
    );

    return html;
  }

  function _tsToSecs(ts) {
    const parts = ts.split(':').map(Number);
    if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
    if (parts.length === 2) return parts[0] * 60 + parts[1];
    return 0;
  }

  function _appendTyping() {
    const id  = `typing-${Date.now()}`;
    const div = document.createElement('div');
    div.id = id;
    div.className = 'chat-row system fade-up';
    div.innerHTML = `
      <div class="chat-avatar"><i class="fas fa-brain"></i></div>
      <div class="chat-bubble chat-bubble-typing">
        <div class="chat-typing"><span></span><span></span><span></span></div>
      </div>`;
    const msgs = document.getElementById('chatMessages');
    msgs.appendChild(div);
    msgs.scrollTop = msgs.scrollHeight;
    return id;
  }

  function _removeTyping(id) { document.getElementById(id)?.remove(); }

  function _setBtnState(loading) {
    const btn = document.getElementById('sendChatBtn');
    btn.disabled = loading;
    btn.innerHTML = loading
      ? '<i class="fas fa-spinner fa-spin"></i>'
      : '<i class="fas fa-paper-plane"></i>';
  }

  function _emptyHtml() {
    return `<div class="chat-empty">
      <div class="chat-empty-icon"><i class="fas fa-comments"></i></div>
      <div class="chat-empty-title">Ask about this meeting</div>
      <div class="chat-empty-hints">
        <span class="chat-hint" onclick="Chat._fillHint('Summarise the meeting')">Summarise the meeting</span>
        <span class="chat-hint" onclick="Chat._fillHint('What decisions were made?')">What decisions were made?</span>
        <span class="chat-hint" onclick="Chat._fillHint('Show me clips of key moments')">Show me clips of key moments</span>
        <span class="chat-hint" onclick="Chat._fillHint('What are the action items?')">What are the action items?</span>
      </div>
    </div>`;
  }

  /* Public: used by hint chips in the empty state */
  function _fillHint(text) {
    const input = document.getElementById('chatInput');
    input.value = text;
    input.focus();
  }

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

  function _escAttr(str) {
    return String(str)
      .replace(/\\/g,'\\\\').replace(/'/g,"\\'").replace(/"/g,'&quot;').replace(/\n/g,' ');
  }

  return { init, resetUI, _fillHint };
})();


/* ── Sources — right-panel source cards ─────────────────────────── */
const Sources = (() => {

  function render(sources) {
    const panel = document.getElementById('sourcesPanel');
    panel.classList.remove('hidden');
    const list  = document.getElementById('sourcesList');
    const jobId = State.get('currentJobId');

    list.innerHTML = sources.map(s => {
      const start = s.start ?? 0;
      const end   = s.end   ?? 0;
      const label = `${s.start_timestamp || _fmtSecs(start)} – ${s.end_timestamp || _fmtSecs(end)}`;
      const hasClip = jobId && (end - start) > 0;

      return `
        <div class="source-card">
          <div class="source-meta">
            <span class="source-ts"
                  onclick="Video.seekTo('${s.start_timestamp || _fmtSecs(start)}')"
                  title="Seek to this moment"
                  style="cursor:pointer">
              <i class="fas fa-clock"></i> ${_esc(label)}
            </span>
            ${s.score ? `<span class="source-score">${(s.score * 100).toFixed(0)}%</span>` : ''}
            ${s.primary_speaker && s.primary_speaker !== 'Unknown'
              ? `<span class="source-speaker">${_esc(s.primary_speaker)}</span>` : ''}
          </div>
          <div class="source-text">${_esc(s.text || '')}</div>
          ${hasClip ? `
          <div class="source-clip-actions">
            <button class="source-clip-btn"
                    onclick="Clips.playClip(${start}, ${end}, '${_escAttr(label)}')"
                    title="Play clip">
              <i class="fas fa-scissors"></i> Clip
            </button>
            <button class="source-seek-btn"
                    onclick="Clips.seekMain(${start})"
                    title="Seek in full video">
              <i class="fas fa-forward"></i> Seek
            </button>
          </div>` : ''}
        </div>`;
    }).join('');
  }

  function clear() {
    document.getElementById('sourcesPanel')?.classList.add('hidden');
    const list = document.getElementById('sourcesList');
    if (list) list.innerHTML = '';
  }

  function _esc(str) {
    return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  function _escAttr(str) {
    return String(str)
      .replace(/\\/g,'\\\\').replace(/'/g,"\\'").replace(/"/g,'&quot;').replace(/\n/g,' ');
  }

  function _fmtSecs(secs) {
    const s = Math.floor(secs || 0);
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    return h > 0
      ? `${h}:${String(m).padStart(2,'0')}:${String(sec).padStart(2,'0')}`
      : `${m}:${String(sec).padStart(2,'0')}`;
  }

  return { render, clear };
})();
