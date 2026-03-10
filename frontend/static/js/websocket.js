/* ── websocket.js — WebSocket real-time updates ──────────────────── */

const WebSocketManager = (() => {
  let ws = null;
  let reconnectAttempts = 0;
  const maxReconnectAttempts = 5;
  let reconnectTimeout = null;

  /* ── Connect to WebSocket ─────────────────────────────────────── */
  function connect(jobId) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      return; // Already connected
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/${jobId}`;

    try {
      ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        console.log('WebSocket connected for job:', jobId);
        reconnectAttempts = 0;
        UI.toast('Real-time updates connected', 'success');
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          handleMessage(data);
        } catch (e) {
          console.error('Failed to parse WebSocket message:', e);
        }
      };

      ws.onclose = () => {
        console.log('WebSocket disconnected');
        // Auto-reconnect for active jobs
        if (State.get('currentJobId') === jobId) {
          attemptReconnect(jobId);
        }
      };

      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
      };

    } catch (e) {
      console.error('Failed to create WebSocket:', e);
    }
  }

  /* ── Handle incoming messages ─────────────────────────────────── */
  function handleMessage(data) {
    switch (data.type) {
      case 'progress':
        handleProgressUpdate(data);
        break;
      case 'error':
        handleErrorUpdate(data);
        break;
      case 'ping':
        // Respond to ping to keep connection alive
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send('pong');
        }
        break;
      default:
        console.log('Unknown message type:', data.type);
    }
  }

  /* ── Handle progress updates ──────────────────────────────────── */
  function handleProgressUpdate(data) {
    const { job_id, status, step, progress } = data;

    // Update UI with enhanced progress information
    UI.updateProcessingStatus(status, step, progress);

    // Update job card
    Jobs.updateJobCard(job_id, { status, step, progress });

    // Handle completion
    if (status === 'completed') {
      UI.hideOverlay();
      UI.toast('Processing complete! ✨', 'success');
      // Reload the job data
      Jobs.loadAndRender(job_id);
    } else if (status === 'failed') {
      UI.hideOverlay();
      UI.toast(`Processing failed: ${step}`, 'error');
    }
  }

  /* ── Handle error updates ─────────────────────────────────────── */
  function handleErrorUpdate(data) {
    const { job_id, error } = data;

    // Update UI with error
    UI.updatePipeline('failed');
    UI.setProgress(0);
    UI.hideOverlay();

    // Update job card
    Jobs.updateJobCard(job_id, { status: 'failed', step: `Error: ${error}` });

    // Show error toast
    UI.toast(`Processing failed: ${error}`, 'error');
  }

  /* ── Attempt to reconnect ─────────────────────────────────────── */
  function attemptReconnect(jobId) {
    if (reconnectAttempts >= maxReconnectAttempts) {
      console.log('Max reconnect attempts reached');
      UI.toast('Lost real-time connection', 'warning');
      return;
    }

    reconnectAttempts++;
    const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 30000);

    console.log(`Attempting to reconnect in ${delay}ms (attempt ${reconnectAttempts})`);

    reconnectTimeout = setTimeout(() => {
      connect(jobId);
    }, delay);
  }

  /* ── Disconnect ───────────────────────────────────────────────── */
  function disconnect() {
    if (reconnectTimeout) {
      clearTimeout(reconnectTimeout);
      reconnectTimeout = null;
    }

    if (ws) {
      ws.close();
      ws = null;
    }

    reconnectAttempts = 0;
  }

  /* ── Public API ───────────────────────────────────────────────── */
  return {
    connect,
    disconnect
  };
})();