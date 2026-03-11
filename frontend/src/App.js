import React, { useState, useEffect, useRef, useCallback } from 'react';
import { api } from './utils/api';
import { useWebSocket } from './hooks/useWebSocket';

// ── markdown renderer ──────────────────────────────────────────────────────
function renderMarkdown(text) {
  if (!text) return '';

  // Step 1: escape HTML entities
  let html = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  // Step 2: headings (must run before inline processing)
  html = html
    .replace(/^### (.+)$/gm, '<h4 class="text-sm font-bold text-slate-100 mt-3 mb-1">$1</h4>')
    .replace(/^## (.+)$/gm,  '<h3 class="text-base font-bold text-white mt-4 mb-1">$1</h3>')
    .replace(/^# (.+)$/gm,   '<h2 class="text-lg font-bold text-white mt-4 mb-2">$1</h2>');

  // Step 3: collect consecutive bullet lines into <ul> blocks
  html = html.replace(
    /((?:^[-•*] .+$\n?)+)/gm,
    match => {
      const items = match.trim().split('\n').map(line =>
        `<li class="ml-1 text-slate-300 leading-relaxed py-0.5">${line.replace(/^[-•*] /, '')}</li>`
      ).join('');
      return `<ul class="list-disc pl-5 my-1.5 space-y-0.5">${items}</ul>`;
    }
  );

  // Step 4: collect consecutive numbered lines into <ol> blocks
  html = html.replace(
    /((?:^\d+\. .+$\n?)+)/gm,
    match => {
      const items = match.trim().split('\n').map(line =>
        `<li class="ml-1 text-slate-300 leading-relaxed py-0.5">${line.replace(/^\d+\. /, '')}</li>`
      ).join('');
      return `<ol class="list-decimal pl-5 my-1.5 space-y-0.5">${items}</ol>`;
    }
  );

  // Step 5: inline formatting
  html = html
    .replace(/\*\*(.+?)\*\*/g, '<strong class="text-white font-semibold">$1</strong>')
    .replace(/`(.+?)`/g, '<code class="bg-slate-700 px-1.5 py-0.5 rounded text-xs font-mono text-emerald-300">$1</code>')
    .replace(/\[(\d{1,2}:\d{2}(?::\d{2})?)\]/g,
      '<span class="ts-link cursor-pointer text-indigo-400 underline font-mono text-xs hover:text-indigo-300 transition-colors" data-ts="$1">[$1]</span>');

  // Step 6: newlines → <br/> only outside of block-level tags
  // Split on existing block tags, convert \n only in text segments
  html = html.split(/(<(?:ul|ol|h[1-4]|li)[^>]*>.*?<\/(?:ul|ol|h[1-4]|li)>)/gs).map((segment, i) => {
    // odd indices are matched block tags — leave them alone
    if (i % 2 === 1) return segment;
    return segment.replace(/\n/g, '<br/>');
  }).join('');

  return html;
}

// ── speaker colours ────────────────────────────────────────────────────────
const SPEAKER_COLORS = [
  'bg-indigo-500/20 text-indigo-300 border-indigo-500/30',
  'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
  'bg-amber-500/20 text-amber-300 border-amber-500/30',
  'bg-rose-500/20 text-rose-300 border-rose-500/30',
  'bg-violet-500/20 text-violet-300 border-violet-500/30',
  'bg-sky-500/20 text-sky-300 border-sky-500/30',
  'bg-pink-500/20 text-pink-300 border-pink-500/30',
];
const _colorCache = {};
let _colorIdx = 0;
function speakerColor(name) {
  if (!_colorCache[name]) _colorCache[name] = SPEAKER_COLORS[_colorIdx++ % SPEAKER_COLORS.length];
  return _colorCache[name];
}

// ── format seconds → HH:MM:SS or M:SS ─────────────────────────────────────
function fmtTime(s) {
  const t = Math.floor(s || 0);
  const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), sec = t % 60;
  return h > 0
    ? `${h}:${String(m).padStart(2,'0')}:${String(sec).padStart(2,'0')}`
    : `${m}:${String(sec).padStart(2,'0')}`;
}

// ── CLIP CARD ──────────────────────────────────────────────────────────────
function ClipCard({ jobId, source, onSeek }) {
  const [clipUrl, setClipUrl] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState(null);
  const [expanded, setExpanded] = useState(false);

  const speaker = source.primary_speaker || 'Unknown';
  const startTs = source.start_timestamp || '?';
  const endTs   = source.end_timestamp   || '?';

  async function load() {
    if (clipUrl || loading) return;
    setLoading(true); setError(null);
    try {
      const res = await api.clip(jobId, source.start, source.end);
      setClipUrl(res.clip_url);
    } catch (err) {
      setError('Failed to generate clip — check FFmpeg is installed');
    } finally {
      setLoading(false);
    }
  }

  function toggle() {
    setExpanded(prev => { if (!prev) load(); return !prev; });
  }

  return (
    <div className="rounded-xl border border-slate-600/70 bg-slate-800/60 overflow-hidden mb-2 shadow-sm">
      <button
        onClick={toggle}
        className="w-full flex items-center gap-2 px-3 py-2.5 hover:bg-slate-700/40 transition-colors text-left"
      >
        <span className="text-slate-400 text-sm">{expanded ? '▾' : '▸'}</span>
        <span className="font-mono text-xs text-indigo-300 bg-indigo-500/10 border border-indigo-500/20 px-2 py-0.5 rounded-md shrink-0">
          {startTs} – {endTs}
        </span>
        <span className={`text-xs font-medium px-2 py-0.5 rounded-full border shrink-0 ${speakerColor(speaker)}`}>
          {speaker}
        </span>
        <span className="flex-1 text-xs text-slate-400 truncate italic">{source.text?.slice(0, 80)}…</span>
        <span className={`text-xs font-medium shrink-0 transition-colors ${expanded ? 'text-slate-400' : 'text-indigo-400 hover:text-indigo-300'}`}>
          {expanded ? 'close' : '▶ play'}
        </span>
      </button>

      {expanded && (
        <div className="border-t border-slate-700/60 px-3 pb-3 pt-2 bg-slate-900/40">
          {loading && (
            <div className="flex items-center gap-2 text-xs text-slate-400 py-3">
              <span className="w-3 h-3 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin" />
              Generating clip with FFmpeg…
            </div>
          )}
          {error && <div className="text-xs text-red-400 py-2 bg-red-500/5 rounded px-2">{error}</div>}
          {clipUrl && (
            <div className="space-y-2 pt-1">
              <video src={clipUrl} controls autoPlay className="w-full rounded-lg bg-black shadow" style={{ maxHeight: 260 }} />
              <div className="flex gap-2 flex-wrap">
                <a href={clipUrl} download
                  className="text-xs px-3 py-1.5 rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-300 transition border border-slate-600">
                  ⬇ Download clip
                </a>
                {onSeek && (
                  <button onClick={() => onSeek(source.start)}
                    className="text-xs px-3 py-1.5 rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-300 transition border border-slate-600">
                    ⏩ Seek in main video
                  </button>
                )}
              </div>
              <p className="text-xs text-slate-500 leading-relaxed border-t border-slate-700/60 pt-2">{source.text}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── PIPELINE BAR ───────────────────────────────────────────────────────────
function PipelineBar({ status, step }) {
  const steps   = ['uploaded', 'transcribing', 'chunking', 'indexing', 'generating_mom', 'completed'];
  const labels  = ['Upload', 'Transcribe', 'Chunk', 'Embed', 'MoM', 'Ready'];
  const icons   = ['📁', '🎙', '✂️', '🔮', '📋', '✅'];
  const curIdx  = steps.indexOf(status);

  return (
    <div className="px-4 py-2.5 bg-slate-800/50 border-b border-slate-700/80 shrink-0">
      <div className="flex items-center gap-0 overflow-x-auto">
        {steps.map((s, i) => {
          const done   = i < curIdx || status === 'completed';
          const active = i === curIdx && status !== 'completed' && status !== 'failed';
          const failed = status === 'failed' && i === curIdx;
          return (
            <React.Fragment key={s}>
              <div className="flex items-center gap-1.5 shrink-0">
                <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs border transition-all duration-300
                  ${failed  ? 'bg-red-500 border-red-400 text-white' :
                    done    ? 'bg-emerald-500/80 border-emerald-400 text-white' :
                    active  ? 'bg-indigo-500 border-indigo-400 text-white ring-2 ring-indigo-400/30' :
                              'bg-slate-800 border-slate-600 text-slate-500'}`}>
                  {done ? '✓' : failed ? '✗' : active ? <span className="animate-pulse">{icons[i]}</span> : <span className="text-[10px]">{i+1}</span>}
                </div>
                <span className={`text-xs whitespace-nowrap font-medium
                  ${done ? 'text-emerald-400' : active ? 'text-indigo-300' : failed ? 'text-red-400' : 'text-slate-600'}`}>
                  {labels[i]}
                </span>
              </div>
              {i < steps.length - 1 && (
                <div className={`h-px flex-1 min-w-3 mx-1.5 transition-all duration-500 ${done ? 'bg-emerald-500/40' : 'bg-slate-700'}`} />
              )}
            </React.Fragment>
          );
        })}
      </div>
      {step && status !== 'completed' && status !== 'failed' && (
        <div className="text-xs text-slate-500 mt-1.5 truncate">{step}</div>
      )}
    </div>
  );
}

// ── TRANSCRIPT TAB ─────────────────────────────────────────────────────────
function TranscriptTab({ transcript, onSeek }) {
  const [search, setSearch] = useState('');
  const [activeIdx, setActiveIdx] = useState(null);

  const segs = transcript?.speaker_segments?.length
    ? transcript.speaker_segments
    : transcript?.segments || [];

  const filtered = search.trim()
    ? segs.filter(seg => seg.text?.toLowerCase().includes(search.toLowerCase()))
    : segs;

  function highlight(text) {
    if (!search.trim()) return text;
    const re = new RegExp(`(${search.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')})`, 'gi');
    return text.replace(re, '<mark class="bg-amber-400/30 text-amber-200 rounded px-0.5">$1</mark>');
  }

  if (!segs.length) {
    return <div className="p-6 text-slate-500 text-sm flex flex-col items-center gap-2 mt-8">
      <span className="text-2xl opacity-30">📝</span>
      No transcript segments available.
    </div>;
  }

  return (
    <div className="flex flex-col h-full">
      {/* Search bar */}
      <div className="px-3 py-2 border-b border-slate-700/60 bg-slate-800/30 shrink-0">
        <div className="relative">
          <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500 text-xs">🔍</span>
          <input
            className="w-full bg-slate-800 border border-slate-700 rounded-lg pl-8 pr-3 py-1.5 text-xs text-white placeholder-slate-500 outline-none focus:border-indigo-500/60 transition"
            placeholder="Search transcript…"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
          {search && (
            <button onClick={() => setSearch('')} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-white text-xs">✕</button>
          )}
        </div>
        {search && (
          <div className="text-xs text-slate-500 mt-1">{filtered.length} result{filtered.length !== 1 ? 's' : ''}</div>
        )}
      </div>

      {/* Segments */}
      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {filtered.map((seg, i) => {
          const speaker = seg.speaker || 'Unknown';
          const isActive = activeIdx === i;
          return (
            <div key={i}
              className={`flex gap-2.5 p-2 rounded-lg transition-colors group cursor-pointer
                ${isActive ? 'bg-indigo-500/10 border border-indigo-500/20' : 'hover:bg-slate-800/60 border border-transparent'}`}
              onClick={() => { setActiveIdx(i); onSeek && onSeek(seg.start ?? 0); }}
            >
              <button
                className="font-mono text-xs text-indigo-400 bg-slate-800 border border-slate-700 px-2 py-0.5 rounded shrink-0 h-fit mt-0.5 hover:bg-indigo-500/20 hover:border-indigo-500/40 transition"
                title="Seek to this moment"
              >
                {fmtTime(seg.start ?? 0)}
              </button>
              <span className={`text-xs font-medium px-2 py-0.5 rounded-full border h-fit mt-0.5 shrink-0 ${speakerColor(speaker)}`}>
                {speaker}
              </span>
              <span
                className="text-sm text-slate-300 leading-relaxed"
                dangerouslySetInnerHTML={{ __html: highlight(seg.text || '') }}
              />
            </div>
          );
        })}
        {filtered.length === 0 && search && (
          <div className="text-center text-slate-500 text-sm py-8">No matches for "{search}"</div>
        )}
      </div>
    </div>
  );
}

// ── MOM TAB ────────────────────────────────────────────────────────────────
function MomTab({ mom, jobId }) {
  const [copied, setCopied] = useState(false);

  if (!mom || !Object.keys(mom).length) {
    return <div className="p-6 text-slate-500 text-sm flex flex-col items-center gap-2 mt-8">
      <span className="text-2xl opacity-30">📋</span>
      Minutes of Meeting not yet available.
    </div>;
  }

  function downloadJson() {
    const blob = new Blob([JSON.stringify(mom, null, 2)], { type: 'application/json' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href = url; a.download = `mom-${jobId || 'meeting'}.json`;
    a.click(); URL.revokeObjectURL(url);
  }

  function copyText() {
    const lines = [];
    if (mom.title)   lines.push(`# ${mom.title}\n`);
    if (mom.summary) lines.push(`## Summary\n${mom.summary}\n`);
    if (mom.agenda?.length) {
      lines.push('## Agenda');
      mom.agenda.forEach(a => lines.push(`• ${typeof a === 'string' ? a : JSON.stringify(a)}`));
      lines.push('');
    }
    if (mom.key_points?.length) {
      lines.push('## Key Points');
      mom.key_points.forEach(kp => lines.push(`[${kp.timestamp}] ${kp.speaker || ''}: ${kp.point || kp}`));
      lines.push('');
    }
    if (mom.decisions?.length) {
      lines.push('## Decisions');
      mom.decisions.forEach(d => lines.push(`[${d.timestamp}] ${d.decision || d}`));
      lines.push('');
    }
    if (mom.action_items?.length) {
      lines.push('## Action Items');
      mom.action_items.forEach(a => lines.push(`[${a.timestamp}] ${a.owner || 'TBD'}: ${a.task || a}`));
    }
    navigator.clipboard.writeText(lines.join('\n'));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="flex flex-col h-full">
      {/* Export toolbar */}
      <div className="flex items-center gap-2 px-4 py-2 border-b border-slate-700/60 bg-slate-800/30 shrink-0">
        <span className="text-xs text-slate-500 flex-1">Minutes of Meeting</span>
        <button onClick={copyText}
          className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-300 transition border border-slate-600">
          {copied ? '✓ Copied' : '📋 Copy text'}
        </button>
        <button onClick={downloadJson}
          className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white transition">
          ⬇ Export JSON
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-5 space-y-5">
        {mom.title && (
          <h2 className="text-xl font-bold text-white border-b border-slate-700/60 pb-3">{mom.title}</h2>
        )}

        {mom.summary && (
          <section>
            <h3 className="section-label">Summary</h3>
            <div className="bg-indigo-500/8 border border-indigo-500/20 rounded-xl p-4 text-sm text-slate-300 leading-relaxed">
              {mom.summary}
            </div>
          </section>
        )}

        {mom.agenda?.length > 0 && (
          <section>
            <h3 className="section-label">Agenda</h3>
            <div className="space-y-1.5">
              {mom.agenda.map((item, i) => (
                <div key={i} className="flex items-start gap-2 bg-slate-800/60 border border-slate-700/40 rounded-lg px-3 py-2 text-sm text-slate-300">
                  <span className="text-indigo-400 text-xs mt-1 shrink-0">◆</span>
                  {typeof item === 'string' ? item : JSON.stringify(item)}
                </div>
              ))}
            </div>
          </section>
        )}

        {mom.key_points?.length > 0 && (
          <section>
            <h3 className="section-label">Key Points <span className="text-slate-600 font-normal normal-case tracking-normal">({mom.key_points.length})</span></h3>
            <div className="space-y-2">
              {mom.key_points.map((kp, i) => (
                <div key={i} className="bg-slate-800/60 border border-slate-700/40 rounded-xl p-3">
                  <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                    {kp.timestamp && <span className="font-mono text-xs text-indigo-400 bg-indigo-500/10 border border-indigo-500/20 px-2 py-0.5 rounded-md">{kp.timestamp}</span>}
                    {kp.speaker && <span className={`text-xs font-medium px-2 py-0.5 rounded-full border ${speakerColor(kp.speaker)}`}>{kp.speaker}</span>}
                  </div>
                  <p className="text-sm text-slate-300 leading-relaxed">{kp.point || kp}</p>
                </div>
              ))}
            </div>
          </section>
        )}

        {mom.decisions?.length > 0 && (
          <section>
            <h3 className="section-label">Decisions <span className="text-slate-600 font-normal normal-case tracking-normal">({mom.decisions.length})</span></h3>
            <div className="space-y-2">
              {mom.decisions.map((d, i) => (
                <div key={i} className="flex gap-3 bg-emerald-500/8 border border-emerald-500/20 rounded-xl p-3">
                  <span className="text-lg shrink-0">✅</span>
                  <div>
                    {d.timestamp && <span className="font-mono text-xs text-emerald-400 block mb-1">{d.timestamp}</span>}
                    <p className="text-sm text-slate-300 leading-relaxed">{d.decision || d}</p>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {mom.action_items?.length > 0 && (
          <section>
            <h3 className="section-label">Action Items <span className="text-slate-600 font-normal normal-case tracking-normal">({mom.action_items.length})</span></h3>
            <div className="space-y-2">
              {mom.action_items.map((a, i) => (
                <div key={i} className="bg-amber-500/8 border border-amber-500/20 rounded-xl p-3">
                  <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                    {a.timestamp && <span className="font-mono text-xs text-amber-400 bg-amber-500/10 border border-amber-500/20 px-2 py-0.5 rounded-md">{a.timestamp}</span>}
                    {a.owner && <span className="text-xs font-semibold text-amber-300 bg-amber-500/10 border border-amber-500/20 px-2 py-0.5 rounded-full">👤 {a.owner}</span>}
                  </div>
                  <p className="text-sm text-slate-300 leading-relaxed">{a.task || a}</p>
                </div>
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}

// ── CHAT TAB ───────────────────────────────────────────────────────────────
function ChatTab({ jobId, hasVideo, onSeek }) {
  const [messages, setMessages]   = useState([]);
  const [input, setInput]         = useState('');
  const [busy, setBusy]           = useState(false);
  const [history, setHistory]     = useState([]);
  const bottomRef                 = useRef(null);
  const inputRef                  = useRef(null);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  async function send(question) {
    const q = (question || input).trim();
    if (!q || busy) return;
    setInput('');
    setBusy(true);

    const msgId = `msg-${Date.now()}`;
    setMessages(prev => [
      ...prev,
      { id: `${msgId}-u`, role: 'user', content: q },
      { id: msgId, role: 'assistant', content: '', streaming: true },
    ]);

    let fullAnswer = '';

    try {
      for await (const event of api.chatStream(jobId, q, history.slice(-12))) {
        if (event.type === 'token') {
          fullAnswer += event.token;
          setMessages(prev => prev.map(m => m.id === msgId ? { ...m, content: fullAnswer } : m));
        } else if (event.type === 'sources') {
          setMessages(prev => prev.map(m => m.id === msgId ? { ...m, sources: event.sources, wants_clip: false } : m));
        } else if (event.type === 'clips') {
          const wantsClip = hasVideo && event.clips?.length > 0;
          setMessages(prev => prev.map(m => m.id === msgId ? { ...m, sources: event.clips, wants_clip: wantsClip } : m));
        } else if (event.type === 'followups') {
          setMessages(prev => prev.map(m => m.id === msgId ? { ...m, followups: event.followups } : m));
        } else if (event.type === 'error') {
          setMessages(prev => prev.map(m => m.id === msgId ? { ...m, content: `⚠️ ${event.error}`, streaming: false } : m));
          break;
        } else if (event.type === 'done') {
          setMessages(prev => prev.map(m => m.id === msgId ? { ...m, streaming: false } : m));
          break;
        }
      }
    } catch (err) {
      setMessages(prev => prev.map(m => m.id === msgId
        ? { ...m, content: `⚠️ Error: ${err.message}`, streaming: false } : m));
    }

    setHistory(prev => [...prev,
      { role: 'user', content: q },
      { role: 'assistant', content: fullAnswer },
    ]);
    setBusy(false);
    setTimeout(() => inputRef.current?.focus(), 50);
  }

  function handleClick(e) {
    const ts = e.target.dataset?.ts;
    if (ts && onSeek) {
      const parts = ts.split(':').map(Number);
      const secs = parts.length === 3
        ? parts[0]*3600 + parts[1]*60 + parts[2]
        : parts[0]*60 + parts[1];
      onSeek(secs);
    }
  }

  const QUICK_PROMPTS = [
    { label: '📋 Summarise meeting', q: 'Summarise the meeting' },
    { label: '✅ Key decisions',     q: 'What were the key decisions?' },
    { label: '📌 Action items',      q: 'List all action items with owners' },
    { label: '🎙 Who attended?',     q: 'Who were the speakers in this meeting?' },
    { label: '🎬 Show intro clip',   q: 'Show me clip when the meeting started' },
  ];

  return (
    <div className="flex flex-col h-full bg-slate-900">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 min-h-0">

        {/* Empty state */}
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full gap-5 pb-8">
            <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-indigo-500/20 to-violet-500/20 border border-indigo-500/20 flex items-center justify-center text-2xl">
              🧠
            </div>
            <div className="text-center">
              <p className="text-slate-300 font-medium">AI Meeting Assistant</p>
              <p className="text-slate-500 text-sm mt-1">Ask anything about this meeting</p>
            </div>
            <div className="flex flex-wrap gap-2 justify-center max-w-sm">
              {QUICK_PROMPTS.map(p => (
                <button key={p.q} onClick={() => send(p.q)}
                  className="text-xs px-3 py-2 rounded-xl bg-slate-800 border border-slate-700 hover:border-indigo-500/50 hover:bg-slate-700/60 hover:text-indigo-300 text-slate-400 transition">
                  {p.label}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Message list */}
        {messages.map((msg) => (
          <div key={msg.id} className={`flex gap-2.5 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            {msg.role === 'assistant' && (
              <div className="w-7 h-7 rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-xs shrink-0 mt-1 shadow">
                🧠
              </div>
            )}

            <div className={`max-w-[88%] flex flex-col gap-2 ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
              {/* Bubble */}
              <div className={`px-4 py-2.5 rounded-2xl text-sm leading-relaxed shadow-sm
                ${msg.role === 'user'
                  ? 'bg-indigo-600 text-white rounded-br-sm'
                  : 'bg-slate-800 border border-slate-700/80 text-slate-200 rounded-bl-sm'}`}>
                {msg.role === 'assistant' ? (
                  <div>
                    <div onClick={handleClick}
                      dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.content || '') }} />
                    {/* Streaming cursor */}
                    {msg.streaming && (
                      <span className="inline-block w-0.5 h-4 bg-indigo-400 animate-pulse ml-0.5 align-text-bottom rounded" />
                    )}
                  </div>
                ) : msg.content}
              </div>

              {/* Clip cards */}
              {msg.wants_clip && msg.sources?.length > 0 && (
                <div className="w-full space-y-1 mt-1">
                  <div className="flex items-center gap-2 text-xs text-indigo-300 font-medium px-1 pb-1.5">
                    <span>🎬</span>
                    <span>{msg.sources.length} clip{msg.sources.length !== 1 ? 's' : ''} found</span>
                  </div>
                  {msg.sources.map((src, si) => (
                    <ClipCard key={si} jobId={jobId} source={src} onSeek={onSeek} />
                  ))}
                </div>
              )}

              {/* Source chips (non-clip) */}
              {!msg.wants_clip && msg.sources?.length > 0 && onSeek && !msg.streaming && (
                <div className="flex flex-wrap gap-1.5 px-0.5">
                  <span className="text-xs text-slate-600 w-full">Sources:</span>
                  {msg.sources.slice(0, 3).map((src, si) => (
                    <button key={si} onClick={() => onSeek(src.start)}
                      className="text-xs font-mono px-2 py-0.5 rounded-full bg-slate-800 hover:bg-indigo-500/15 text-slate-500 hover:text-indigo-300 border border-slate-700 hover:border-indigo-500/40 transition"
                      title={src.text?.slice(0, 120)}>
                      [{src.start_timestamp}]
                    </button>
                  ))}
                </div>
              )}

              {/* Follow-up suggestion chips */}
              {msg.followups?.length > 0 && !msg.streaming && (
                <div className="flex flex-col gap-1.5 w-full mt-1">
                  <span className="text-xs text-slate-500 px-0.5 font-medium">💡 Follow up:</span>
                  <div className="flex flex-col gap-1.5">
                    {msg.followups.map((q, fi) => (
                      <button key={fi} onClick={() => send(q)}
                        className="text-xs px-3 py-2 rounded-xl bg-slate-800/80 border border-slate-700 hover:border-indigo-500/50 hover:bg-slate-700/60 hover:text-indigo-300 text-slate-400 transition text-left leading-relaxed">
                        → {q}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {msg.role === 'user' && (
              <div className="w-7 h-7 rounded-full bg-slate-700 border border-slate-600 flex items-center justify-center text-xs shrink-0 mt-1">
                👤
              </div>
            )}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input bar */}
      <div className="border-t border-slate-700/80 p-3 bg-slate-800/60 shrink-0">
        <div className="flex gap-2">
          <input
            ref={inputRef}
            className="flex-1 bg-slate-700/80 border border-slate-600 rounded-xl px-3.5 py-2.5 text-sm text-white placeholder-slate-400 outline-none focus:border-indigo-500/70 focus:bg-slate-700 transition"
            placeholder={hasVideo ? "Ask about meeting or 'show me clip when…'" : "Ask anything about the meeting…"}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && !e.shiftKey && send()}
            disabled={busy}
          />
          <button onClick={() => send()}
            disabled={busy || !input.trim()}
            className="w-10 h-10 flex items-center justify-center bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-700 disabled:text-slate-500 text-white rounded-xl transition shadow-sm font-medium text-lg">
            {busy ? <span className="w-3 h-3 border-2 border-white/40 border-t-white rounded-full animate-spin" /> : '↑'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── JOB VIEW ───────────────────────────────────────────────────────────────
function JobView({ job, onBack }) {
  const [activeTab, setActiveTab] = useState('transcript');
  const videoRef = useRef(null);

  function seekTo(secs) {
    if (!videoRef.current) return;
    videoRef.current.currentTime = secs;
    videoRef.current.play().catch(() => {});
    const panel = videoRef.current.closest('.video-panel');
    if (panel) {
      panel.classList.add('ring-2', 'ring-indigo-500');
      setTimeout(() => panel.classList.remove('ring-2', 'ring-indigo-500'), 800);
    }
  }

  const hasVideo = !!job.source_video;

  useEffect(() => {
    if (videoRef.current && job.source_video) videoRef.current.load();
  }, [job.source_video]);

  // Auto-switch to transcript when ready
  useEffect(() => {
    if (job.transcript_available && activeTab === 'transcript') return;
    if (job.status === 'completed' && !job.transcript_available) setActiveTab('mom');
  }, [job.status, job.transcript_available]);

  const tabs = [
    { id: 'transcript', label: '📝 Transcript', available: job.transcript_available },
    { id: 'mom',        label: '📋 Minutes',    available: job.mom_available },
    { id: 'chat',       label: '💬 AI Chat',    available: job.status === 'completed' },
  ];

  const statusColor = {
    completed:      'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
    failed:         'bg-red-500/15 text-red-300 border-red-500/30',
    transcribing:   'bg-blue-500/15 text-blue-300 border-blue-500/30',
    chunking:       'bg-amber-500/15 text-amber-300 border-amber-500/30',
    indexing:       'bg-purple-500/15 text-purple-300 border-purple-500/30',
    generating_mom: 'bg-indigo-500/15 text-indigo-300 border-indigo-500/30',
  }[job.status] || 'bg-slate-700 text-slate-400 border-slate-600';

  // Duration display
  const dur = job.duration_seconds;
  const durStr = dur ? (dur >= 3600
    ? `${Math.floor(dur/3600)}h ${Math.floor((dur%3600)/60)}m`
    : `${Math.floor(dur/60)}m ${Math.round(dur%60)}s`) : null;

  return (
    <div className="flex flex-col h-full overflow-hidden bg-slate-900">
      {/* Header */}
      <div className="flex items-center gap-3 px-5 py-3 bg-slate-950/80 border-b border-slate-800 shrink-0">
        <button onClick={onBack}
          className="flex items-center gap-1 text-slate-400 hover:text-white transition text-sm px-2 py-1 rounded-lg hover:bg-slate-800">
          ← Back
        </button>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-semibold text-white truncate">{job.filename}</div>
          <div className="flex items-center gap-2 text-xs text-slate-500 mt-0.5">
            <span>{new Date(job.created_at).toLocaleString()}</span>
            {durStr && <><span>·</span><span>{durStr}</span></>}
            {job.chunk_count > 0 && <><span>·</span><span>{job.chunk_count} chunks</span></>}
          </div>
        </div>
        <span className={`text-xs px-2.5 py-1 rounded-full font-medium capitalize border ${statusColor}`}>
          {job.status.replace(/_/g, ' ')}
        </span>
      </div>

      <PipelineBar status={job.status} step={job.step} />

      {/* Error banner */}
      {job.status === 'failed' && (
        <div className="mx-4 mt-3 px-4 py-3 bg-red-500/8 border border-red-500/25 rounded-xl text-sm text-red-300 flex items-start gap-2 shrink-0">
          <span className="text-red-400 shrink-0 mt-0.5">✖</span>
          <div>
            <strong className="text-red-200">Processing failed</strong>
            {job.error && <p className="mt-0.5 text-red-400/70 text-xs font-mono break-all">{job.error}</p>}
          </div>
        </div>
      )}

      {/* Body */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left panel: tabs */}
        <div className="flex flex-col flex-1 min-w-0 overflow-hidden border-r border-slate-700/60">
          {/* Tab bar */}
          <div className="flex border-b border-slate-700/60 bg-slate-800/40 shrink-0">
            {tabs.map(t => (
              <button key={t.id}
                onClick={() => t.available && setActiveTab(t.id)}
                className={`px-5 py-3 text-xs font-medium border-b-2 transition-all whitespace-nowrap
                  ${activeTab === t.id
                    ? 'border-indigo-500 text-indigo-300 bg-indigo-500/5'
                    : t.available
                      ? 'border-transparent text-slate-500 hover:text-slate-300 hover:border-slate-500'
                      : 'border-transparent text-slate-700 cursor-not-allowed'}`}>
                {t.label}
                {!t.available && job.status !== 'completed' && (
                  <span className="ml-1 opacity-50">⏳</span>
                )}
              </button>
            ))}
          </div>

          {/* Tab content */}
          <div className="flex-1 overflow-hidden">
            {activeTab === 'transcript' && (
              job.transcript_available && job.transcript
                ? <TranscriptTab transcript={job.transcript} onSeek={seekTo} />
                : <EmptyTabMsg status={job.status} tab="transcript" />
            )}
            {activeTab === 'mom' && (
              job.mom_available && job.mom
                ? <MomTab mom={job.mom} jobId={job.job_id} />
                : <EmptyTabMsg status={job.status} tab="mom" />
            )}
            {activeTab === 'chat' && (
              job.status === 'completed'
                ? <ChatTab key={job.job_id} jobId={job.job_id} hasVideo={hasVideo} onSeek={seekTo} />
                : <EmptyTabMsg status={job.status} tab="chat" />
            )}
          </div>
        </div>

        {/* Right panel: video */}
        <div className="w-72 shrink-0 flex flex-col bg-slate-900/60 border-l border-slate-700/30">
          <div className="px-3 py-2.5 text-xs font-semibold uppercase tracking-widest text-slate-500 border-b border-slate-700/60">
            🎬 Video
          </div>
          {hasVideo ? (
            <div className="p-3 video-panel rounded-lg transition-all duration-200">
              <video ref={videoRef} src={job.source_video} controls preload="metadata"
                className="w-full rounded-xl bg-black aspect-video shadow-lg" />
              <p className="text-xs text-slate-600 mt-2 text-center leading-relaxed">
                Timestamps in chat and transcript<br/>seek this video automatically
              </p>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center flex-1 text-slate-600 text-sm gap-3 p-6 text-center">
              <span className="text-4xl opacity-20">🎥</span>
              <span className="text-slate-500 font-medium">No video</span>
              <span className="text-xs opacity-60 leading-relaxed">Upload a video file to enable clip playback</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function EmptyTabMsg({ status, tab }) {
  const msgs = {
    transcript: { waiting: 'Transcript will appear after transcription completes.', done: 'Transcript not available.' },
    mom:        { waiting: 'Minutes will appear after AI analysis completes.',       done: 'Minutes not available.' },
    chat:       { waiting: 'AI Chat is available once processing is complete.',      done: 'Chat not available.' },
  };
  const m = msgs[tab] || {};
  return (
    <div className="p-6 text-slate-500 text-sm flex flex-col items-center gap-2 mt-8">
      <span className="text-2xl opacity-30">{status !== 'completed' ? '⏳' : '⚠️'}</span>
      {status !== 'completed' ? m.waiting : m.done}
    </div>
  );
}

// ── JOB LIST ───────────────────────────────────────────────────────────────
function JobList({ jobs, onSelect, activeId }) {
  const dotCls = s =>
    s === 'completed' ? 'bg-emerald-400 shadow-[0_0_5px_#34d399]'
    : s === 'failed'  ? 'bg-red-400'
    : 'bg-amber-400 animate-pulse';

  return (
    <div className="flex-1 overflow-y-auto px-2 py-2 space-y-0.5">
      {jobs.map(job => (
        <button key={job.job_id} onClick={() => onSelect(job.job_id)}
          className={`w-full text-left px-3 py-2.5 rounded-xl border transition
            ${job.job_id === activeId
              ? 'bg-indigo-500/12 border-indigo-500/25 shadow-sm'
              : 'border-transparent hover:bg-slate-800/70 hover:border-slate-700/60'}`}>
          <div className="flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full shrink-0 ${dotCls(job.status)}`} />
            <span className="text-xs font-medium text-slate-200 truncate flex-1">{job.filename}</span>
          </div>
          <div className="text-xs text-slate-500 mt-0.5 ml-4">
            {job.status.replace(/_/g, ' ')}
            {job.duration_seconds ? ` · ${Math.floor(job.duration_seconds/60)}m` : ''}
          </div>
        </button>
      ))}
    </div>
  );
}

// ── UPLOAD SECTION ─────────────────────────────────────────────────────────
function UploadSection({ onUploaded }) {
  const [file, setFile]           = useState(null);
  const [dragging, setDragging]   = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError]         = useState('');
  const inputRef                  = useRef(null);

  function pick(f) { if (!f) return; setFile(f); setError(''); }

  async function submit() {
    if (!file || uploading) return;
    setUploading(true); setError('');
    try {
      const data = await api.upload(file);
      setFile(null);
      if (inputRef.current) inputRef.current.value = '';
      onUploaded(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="p-3">
      <div
        onDragOver={e => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={e => { e.preventDefault(); setDragging(false); pick(e.dataTransfer.files[0]); }}
        onClick={() => inputRef.current?.click()}
        className={`border-2 border-dashed rounded-xl p-4 text-center cursor-pointer transition-all
          ${dragging ? 'border-indigo-400 bg-indigo-500/10 scale-[1.01]'
                     : file ? 'border-indigo-500/50 bg-indigo-500/5'
                            : 'border-slate-700 hover:border-slate-500 bg-slate-800/30'}`}>
        <input ref={inputRef} type="file" className="hidden"
          accept="video/*,audio/*,.srt,.vtt"
          onChange={e => pick(e.target.files[0])} />
        <div className="text-xl mb-1">{file ? '✅' : '☁️'}</div>
        <div className="text-xs font-medium text-slate-300">
          {file ? file.name : 'Drop file or click to browse'}
        </div>
        <div className="text-xs text-slate-600 mt-0.5">MP4 · MOV · MP3 · SRT · VTT</div>
      </div>

      {error && <p className="text-xs text-red-400 mt-2 bg-red-500/8 px-2 py-1 rounded-lg">{error}</p>}

      <button onClick={submit} disabled={!file || uploading}
        className="mt-2.5 w-full py-2 text-sm font-semibold rounded-xl transition
          bg-indigo-600 hover:bg-indigo-500 active:scale-[.98] disabled:bg-slate-800 disabled:text-slate-600 text-white shadow-sm">
        {uploading ? '⏳ Uploading…' : '🚀 Process Meeting'}
      </button>
    </div>
  );
}

// ── MAIN APP ───────────────────────────────────────────────────────────────
export default function App() {
  const [jobs, setJobs]           = useState([]);
  const [activeJobId, setActiveJobId] = useState(null);
  const [activeJob, setActiveJob] = useState(null);
  const pollRef = useRef(null);

  useEffect(() => { loadJobs(); }, []);

  async function loadJobs() {
    try { const d = await api.jobs(); setJobs(d.jobs || []); }
    catch (e) { console.error('Failed to load jobs:', e); }
  }

  async function selectJob(jobId) {
    setActiveJobId(jobId);
    try { const j = await api.job(jobId); setActiveJob(j); }
    catch (e) { console.error('Failed to load job:', e); }
  }

  function startPolling(jobId) {
    if (pollRef.current) clearInterval(pollRef.current);
    let attempts = 0;
    pollRef.current = setInterval(async () => {
      attempts++;
      try {
        const j = await api.job(jobId);
        setJobs(prev => prev.map(p => p.job_id === jobId ? { ...p, ...j } : p));
        setActiveJob(prev => prev?.job_id === jobId ? j : prev);
        if (j.status === 'completed' || j.status === 'failed') {
          clearInterval(pollRef.current); pollRef.current = null; loadJobs();
        }
      } catch {}
      if (attempts > 300) { clearInterval(pollRef.current); pollRef.current = null; }
    }, 2500);
  }

  const handleWsMessage = useCallback((data) => {
    if (!data?.job_id) return;
    setJobs(prev => prev.map(j =>
      j.job_id === data.job_id
        ? { ...j, status: data.status, step: data.step, progress: data.progress }
        : j
    ));
    setActiveJob(prev =>
      prev?.job_id === data.job_id
        ? { ...prev, status: data.status, step: data.step, progress: data.progress }
        : prev
    );
  }, []);
  const { connect: wsConnect, disconnect: wsDisconnect } = useWebSocket(handleWsMessage);

  function handleUploaded(res) {
    const newJob = {
      job_id: res.job_id, filename: res.filename, file_type: res.file_type,
      status: 'uploaded', step: 'Queued…', progress: 5,
      created_at: new Date().toISOString(),
    };
    setJobs(prev => [newJob, ...prev]);
    selectJob(res.job_id);
    startPolling(res.job_id);
    wsConnect(res.job_id);
  }

  function handleBack() {
    setActiveJobId(null); setActiveJob(null);
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    wsDisconnect();
  }

  return (
    <div className="bg-slate-900 text-white flex flex-col" style={{ height: '100vh' }}>
      {/* Top header */}
      <header className="flex items-center justify-between px-5 py-2.5 bg-slate-950 border-b border-slate-800 shrink-0 z-10">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-sm shadow">🧠</div>
          <div>
            <div className="text-sm font-bold tracking-tight">Meeting Intelligence</div>
            <div className="text-xs text-slate-500">AI-Powered Analysis Platform</div>
          </div>
        </div>
        <div className="flex items-center gap-1.5 text-xs text-emerald-400">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
          Live
        </div>
      </header>

      {/* Body */}
      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar */}
        <aside className="w-60 shrink-0 flex flex-col bg-slate-900 border-r border-slate-800/80 overflow-hidden">
          <div className="border-b border-slate-800/80">
            <div className="px-3 pt-3 pb-0 text-xs font-semibold uppercase tracking-widest text-slate-600">
              Upload
            </div>
            <UploadSection onUploaded={handleUploaded} />
          </div>

          <div className="flex flex-col flex-1 overflow-hidden">
            <div className="px-3 pt-3 pb-1 text-xs font-semibold uppercase tracking-widest text-slate-600 shrink-0">
              Meetings ({jobs.length})
            </div>
            {jobs.length === 0 ? (
              <div className="flex-1 flex flex-col items-center justify-center text-slate-600 text-xs gap-2 pb-8">
                <span className="text-2xl opacity-30">📥</span>
                No meetings yet
              </div>
            ) : (
              <JobList
                jobs={jobs}
                onSelect={id => { selectJob(id); startPolling(id); wsConnect(id); }}
                activeId={activeJobId}
              />
            )}
          </div>
        </aside>

        {/* Main panel */}
        <main className="flex-1 overflow-hidden">
          {activeJob ? (
            <JobView job={activeJob} onBack={handleBack} />
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-slate-600 gap-5">
              <div className="w-20 h-20 rounded-3xl bg-gradient-to-br from-slate-800 to-slate-700 border border-slate-700 flex items-center justify-center text-4xl shadow-lg">
                🧠
              </div>
              <div className="text-center">
                <h2 className="text-xl font-bold text-slate-400">Meeting Intelligence Platform</h2>
                <p className="text-sm text-slate-600 mt-1.5 max-w-xs">
                  Upload a recording or transcript to get AI-powered transcription, minutes, and chat.
                </p>
              </div>
              <div className="flex flex-wrap gap-2 justify-center">
                {['🎙 Transcription', '👥 Diarization', '📋 AI Minutes', '💬 Smart Chat', '🎬 Video Clips'].map(f => (
                  <span key={f} className="text-xs px-3 py-1.5 rounded-full bg-slate-800 border border-slate-700 text-slate-500">{f}</span>
                ))}
              </div>
            </div>
          )}
        </main>
      </div>

      {/* Inline styles for section labels */}
      <style>{`
        .section-label {
          font-size: 0.65rem;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.1em;
          color: #64748b;
          margin-bottom: 0.5rem;
        }
      `}</style>
    </div>
  );
}
