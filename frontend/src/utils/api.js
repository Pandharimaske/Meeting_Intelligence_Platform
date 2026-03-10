const API_BASE = '';

export const api = {
  // Upload a file
  async upload(file) {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`${API_BASE}/api/v1/upload`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      throw new Error(`Upload failed: ${response.statusText}`);
    }

    return response.json();
  },

  // Get all jobs
  async jobs(status = null) {
    const url = status
      ? `${API_BASE}/api/v1/jobs?status=${status}`
      : `${API_BASE}/api/v1/jobs`;

    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`Failed to fetch jobs: ${response.statusText}`);
    }

    return response.json();
  },

  // Get a specific job
  async job(jobId) {
    const response = await fetch(`${API_BASE}/api/v1/jobs/${jobId}`);
    if (!response.ok) {
      throw new Error(`Failed to fetch job: ${response.statusText}`);
    }

    return response.json();
  },

  // Get job transcript
  async transcript(jobId) {
    const response = await fetch(`${API_BASE}/api/v1/jobs/${jobId}/transcript`);
    if (!response.ok) {
      throw new Error(`Failed to fetch transcript: ${response.statusText}`);
    }

    return response.json();
  },

  // Get job MoM
  async mom(jobId) {
    const response = await fetch(`${API_BASE}/api/v1/jobs/${jobId}/mom`);
    if (!response.ok) {
      throw new Error(`Failed to fetch MoM: ${response.statusText}`);
    }

    return response.json();
  },

  // Send chat message
  async chat(jobId, message) {
    const response = await fetch(`${API_BASE}/api/v1/jobs/${jobId}/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ message }),
    });

    if (!response.ok) {
      throw new Error(`Chat failed: ${response.statusText}`);
    }

    return response.json();
  },

  // Get video URL
  videoUrl(jobId) {
    return `${API_BASE}/api/v1/jobs/${jobId}/video`;
  },

  // Get clip URL
  clipUrl(jobId, startTime, endTime) {
    return `${API_BASE}/api/v1/jobs/${jobId}/clips/${startTime}/${endTime}`;
  },
};