/* ── api.js — all HTTP communication ────────────────────────────── */

const API_URL = 'http://localhost:8000';

const Api = {
  async get(endpoint) {
    const res = await fetch(`${API_URL}${endpoint}`);
    if (!res.ok) throw new Error(`GET ${endpoint} → ${res.status}`);
    return res.json();
  },

  async post(endpoint, body) {
    const res = await fetch(`${API_URL}${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`POST ${endpoint} → ${res.status}`);
    return res.json();
  },

  async upload(file) {
    const form = new FormData();
    form.append('file', file);
    const res = await fetch(`${API_URL}/api/v1/upload`, { method: 'POST', body: form });
    if (!res.ok) throw new Error(`Upload failed → ${res.status}`);
    return res.json();
  },

  jobs:       ()      => Api.get('/api/v1/jobs'),
  job:        (id)    => Api.get(`/api/v1/jobs/${id}`),
  chat:       (id, q, history) => Api.post(`/api/v1/jobs/${id}/chat`, { question: q, history }),
  videoUrl:   (id)    => `${API_URL}/api/v1/jobs/${id}/video`,
};
