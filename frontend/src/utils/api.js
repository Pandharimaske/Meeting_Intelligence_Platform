const API_BASE = '';

export const api = {

  // ── Upload ──────────────────────────────────────────────────────────────
  async upload(file) {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch(`${API_BASE}/api/v1/upload`, { method: 'POST', body: formData });
    if (!res.ok) { const e = await res.text(); throw new Error(`Upload failed: ${e}`); }
    return res.json();
  },

  // ── Jobs ────────────────────────────────────────────────────────────────
  async jobs(status = null) {
    const url = status ? `${API_BASE}/api/v1/jobs?status=${status}` : `${API_BASE}/api/v1/jobs`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Failed to fetch jobs: ${res.statusText}`);
    return res.json();
  },

  async job(jobId) {
    const res = await fetch(`${API_BASE}/api/v1/jobs/${jobId}`);
    if (!res.ok) throw new Error(`Failed to fetch job: ${res.statusText}`);
    return res.json();
  },

  // ── Transcript / MoM ────────────────────────────────────────────────────
  async transcript(jobId) {
    const res = await fetch(`${API_BASE}/api/v1/jobs/${jobId}/transcript`);
    if (!res.ok) throw new Error(`Failed to fetch transcript: ${res.statusText}`);
    return res.json();
  },

  async mom(jobId) {
    const res = await fetch(`${API_BASE}/api/v1/jobs/${jobId}/mom`);
    if (!res.ok) throw new Error(`Failed to fetch MoM: ${res.statusText}`);
    return res.json();
  },

  // ── Chat (non-streaming fallback) ───────────────────────────────────────
  async chat(jobId, question, history = []) {
    const res = await fetch(`${API_BASE}/api/v1/jobs/${jobId}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, history }),
    });
    if (!res.ok) { const e = await res.text(); throw new Error(`Chat failed: ${e}`); }
    return res.json();
  },

  // ── Streaming Chat (SSE) ────────────────────────────────────────────────
  // Async generator that yields SSE events: { type, token/sources/clips/followups/error }
  async *chatStream(jobId, question, history = []) {
    const res = await fetch(`${API_BASE}/api/v1/jobs/${jobId}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, history }),
    });
    if (!res.ok) { const e = await res.text(); throw new Error(`Chat failed: ${e}`); }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop(); // keep partial last line
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try { yield JSON.parse(line.slice(6)); } catch { /* skip malformed */ }
        }
      }
    }
  },

  // ── Video / Clips ───────────────────────────────────────────────────────
  videoUrl(jobId) {
    return `${API_BASE}/api/v1/jobs/${jobId}/video`;
  },

  clipUrl(jobId, startTime, endTime) {
    return `${API_BASE}/api/v1/jobs/${jobId}/clips/${startTime}/${endTime}`;
  },

  async clip(jobId, startTime, endTime) {
    const res = await fetch(`${API_BASE}/api/v1/jobs/${jobId}/clips/${startTime}/${endTime}`);
    if (!res.ok) throw new Error(`Clip request failed: ${res.statusText}`);
    return res.json();
  },
};
