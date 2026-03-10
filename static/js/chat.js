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

      if (res.sources?.length) Sources.render(res.sources);

    } catch (err) {
      _removeTyping(typingId);
      _appendBubble('system', '⚠ Failed to get a response. Please try again.');
      console.error('chat error', err);
    }

    _busy = false;
    _setBtnState(false);
  }

  /* ── DOM helpers ──────────────────────────────────────────────── */
  function _appendBubble(role, text) {
    const div = document.createElement('div');
    div.className = `chat-row ${role} fade-up`;
    const icon = role === 'user' ? 'fa-user' : 'fa-brain';
    div.innerHTML = `
      <div class="chat-avatar"><i class="fas ${icon}"></i></div>
      <div class="chat-bubble">${_linkify(_esc(text))}</div>`;
    const msgs = document.getElementById('chatMessages');
    const empty = msgs.querySelector('.chat-empty');
    if (empty) empty.remove();
    msgs.appendChild(div);
    msgs.scrollTop = msgs.scrollHeight;
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

  function _removeTyping(id) {
    document.getElementById(id)?.remove();
  }

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

  /* Convert [HH:MM:SS] timestamp refs to styled spans */
  function _linkify(text) {
    return text.replace(/\[(\d{1,2}:\d{2}(?::\d{2})?)\]/g,
      (_, ts) => `<span style="font-family:var(--mono,monospace);font-size:11px;background:rgba(99,102,241,0.15);color:var(--accent-light);padding:1px 6px;border-radius:4px;cursor:pointer" onclick="Video.seekTo('${ts}')">${ts}</span>`);
  }

  return { init, resetUI };
})();

/* ── Sources — right-panel source cards ─────────────────────────── */
const Sources = (() => {

  function render(sources) {
    const panel = document.getElementById('sourcesPanel');
    panel.classList.remove('hidden');
    const list = document.getElementById('sourcesList');
    list.innerHTML = sources.map(s => `
      <div class="source-card">
        <div class="source-meta">
          <span class="source-ts">${s.start_timestamp || ''} – ${s.end_timestamp || ''}</span>
          ${s.score ? `<span class="source-score">${(s.score * 100).toFixed(0)}% match</span>` : ''}
        </div>
        <div class="source-text">${_esc(s.text || '')}</div>
      </div>`).join('');
  }

  function clear() {
    document.getElementById('sourcesPanel')?.classList.add('hidden');
    const list = document.getElementById('sourcesList');
    if (list) list.innerHTML = '';
  }

  function _esc(str) {
    return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  return { render, clear };
})();
