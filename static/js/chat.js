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

      // Only show clips inline if user explicitly asked for a clip
      if (res.wants_clip) {
        Sources.clear();  // Hide side panel
        if (res.sources?.length) {
          _appendClipSources(res.sources, jobId);
        } else {
          // User asked for clip but no sources found
          UI.toast('No video segments found for your query. Try being more specific.', 'info');
        }
      } else {
        // Text-only response: don't show sources
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

  function _appendClipSources(sources, jobId) {
    const msgs = document.getElementById('chatMessages');
    
    sources.forEach((s, idx) => {
      const start = s.start ?? 0;
      const end = s.end ?? 0;
      const label = `${s.start_timestamp || _fmtSecs(start)} – ${s.end_timestamp || _fmtSecs(end)}`;
      const hasClip = jobId && (end - start) > 0;
      const speaker = s.primary_speaker && s.primary_speaker !== 'Unknown' 
        ? s.primary_speaker : 'Unknown';

      const div = document.createElement('div');
      div.className = 'chat-row system fade-up';
      div.style.marginTop = idx === 0 ? '12px' : '8px';

      div.innerHTML = `
        <div class="chat-avatar"><i class="fas fa-quote-left" style="font-size:10px;"></i></div>
        <div class="chat-clip-card">
          <div class="clip-header">
            <span class="clip-time">
              <i class="fas fa-clock" style="font-size:10px;margin-right:3px;"></i>
              ${_esc(label)}
            </span>
            <span class="clip-speaker">${_esc(speaker)}</span>
            ${s.score ? `<span class="clip-score">${(s.score * 100).toFixed(0)}% match</span>` : ''}
          </div>
          <div class="clip-text">${_esc(s.text || '')}</div>
          ${hasClip ? `
          <div class="clip-actions">
            <button class="btn-play-clip"
                    onclick="Clips.playClip(${start}, ${end}, '${_esc(label)}')"
                    title="Generate and play this clip">
              <i class="fas fa-play"></i> Play Clip
            </button>
            <button class="btn-seek"
                    onclick="Clips.seekMain(${start})"
                    title="Jump to this moment in the full video">
              <i class="fas fa-forward"></i> Seek
            </button>
          </div>` : ''}
        </div>`;

      msgs.appendChild(div);
    });

    msgs.scrollTop = msgs.scrollHeight;
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

  /* ── DOM helpers ──────────────────────────────────────────────── */
  function _appendBubble(role, text) {
    const div = document.createElement('div');
    div.className = `chat-row ${role} fade-up`;
    const icon = role === 'user' ? 'fa-user' : 'fa-brain';
    const formattedText = role === 'system' ? _formatText(text) : _esc(text);
    div.innerHTML = `
      <div class="chat-avatar"><i class="fas ${icon}"></i></div>
      <div class="chat-bubble">${_linkify(formattedText)}</div>`;
    const msgs = document.getElementById('chatMessages');
    const empty = msgs.querySelector('.chat-empty');
    if (empty) empty.remove();
    msgs.appendChild(div);
    msgs.scrollTop = msgs.scrollHeight;
  }

  function _formatText(text) {
    let formatted = _esc(text);

    // Convert markdown headers: # Header → <h4>Header</h4>
    formatted = formatted.replace(/^### (.*?)$/gm, '<h4 class="chat-h4">$1</h4>');
    formatted = formatted.replace(/^## (.*?)$/gm, '<h3 class="chat-h3">$1</h3>');
    formatted = formatted.replace(/^# (.*?)$/gm, '<h2 class="chat-h2">$1</h2>');

    // Convert markdown bold: **text** → <strong>text</strong>
    formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong class="highlight-term">$1</strong>');
    
    // Convert markdown italic: *text* → <em>text</em>
    formatted = formatted.replace(/\*(.*?)\*/g, '<em class="text-emphasis">$1</em>');

    // Convert markdown code: `code` → <code>code</code>
    formatted = formatted.replace(/`(.*?)`/g, '<code class="inline-code">$1</code>');

    // Convert bullet lists: • or - at start of line
    formatted = formatted.replace(/^[\s]*[•\-]\s+(.*?)$/gm, '<li class="chat-list-item">$1</li>');
    formatted = formatted.replace(/(<li[^>]*>.*?<\/li>)/s, '<ul class="chat-list">$1</ul>');

    // Convert numbered lists
    formatted = formatted.replace(/^(\d+)\.\s+(.*?)$/gm, '<li class="chat-list-item chat-numbered">$2</li>');
    formatted = formatted.replace(/(<li[^>]*chat-numbered[^>]*>.*?<\/li>)/s, '<ol class="chat-list">$1</ol>');

    // Highlight important keywords (decisions, actions, metrics)
    const keywords = [
      'decision', 'decided', 'action item', 'assigned to', 'owner:', 'deadline',
      'critical', 'important', 'urgent', 'must', 'required', 'mandatory',
      'key point', 'conclusion', 'recommendation', 'note:', 'warning',
      'approved', 'rejected', 'pending', 'completed', 'in progress'
    ];
    
    keywords.forEach(kw => {
      const regex = new RegExp(`(${kw})(?=[\\s\\.,;:!?]|$)`, 'gi');
      formatted = formatted.replace(regex, '<mark class="kw-highlight">$1</mark>');
    });

    // Convert line breaks to proper spacing
    formatted = formatted.replace(/\n\n+/g, '</p><p class="chat-para">');
    formatted = '<p class="chat-para">' + formatted + '</p>';

    return formatted;
  }

  function _appendTyping() {
    const id  = `typing-${Date.now()}`;
    const div = document.createElement('div');
    div.id = id;
    div.className = 'chat-row system fade-up';
    div.innerHTML = `
      <div class="chat-avatar"><i class="fas fa-brain"></i></div>
      <div class="chat-bubble" style="padding:12px 16px">
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
      <i class="fas fa-comments"></i>
      <span>Ask anything about the meeting</span>
    </div>`;
  }

  function _esc(str) {
    return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  /* Convert [HH:MM:SS] timestamp refs to clickable seek spans */
  function _linkify(text) {
    return text.replace(/\[(\d{1,2}:\d{2}(?::\d{2})?)\]/g,
      (_, ts) => `<span class="chat-ts-link" onclick="Video.seekTo('${ts}')" title="Seek to ${ts}">${ts}</span>`);
  }

  return { init, resetUI };
})();


/* ── Sources — right-panel source cards with clip retrieval ──────── */
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
                  title="Seek to ${s.start_timestamp || ''}"
                  style="cursor:pointer">
              <i class="fas fa-clock" style="font-size:9px;margin-right:3px"></i>
              ${_esc(label)}
            </span>
            ${s.score ? `<span class="source-score">${(s.score * 100).toFixed(0)}% match</span>` : ''}
            ${s.primary_speaker && s.primary_speaker !== 'Unknown'
              ? `<span class="source-speaker">${_esc(s.primary_speaker)}</span>` : ''}
          </div>
          <div class="source-text">${_esc(s.text || '')}</div>
          ${hasClip ? `
          <div class="source-clip-actions">
            <button class="source-clip-btn"
                    onclick="Clips.playClip(${start}, ${end}, '${_esc(label)}')"
                    title="Generate and play this clip">
              <i class="fas fa-scissors"></i> Play Clip
            </button>
            <button class="source-seek-btn"
                    onclick="Clips.seekMain(${start})"
                    title="Jump to this moment in the full video">
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
