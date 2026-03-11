import { useRef, useEffect, useCallback } from 'react';

export function useWebSocket(onMessage) {
  const wsRef = useRef(null);
  const jobIdRef = useRef(null);

  const connect = useCallback((jobId) => {
    // Disconnect any existing connection first
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    jobIdRef.current = jobId;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/${jobId}`;

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('[WS] Connected for job:', jobId);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type !== 'ping') {
            onMessage(data);
          }
        } catch (e) {
          console.error('[WS] Failed to parse message:', e);
        }
      };

      ws.onclose = () => {
        console.log('[WS] Disconnected');
        wsRef.current = null;
      };

      ws.onerror = (error) => {
        console.warn('[WS] Error (falling back to polling):', error);
        wsRef.current = null;
      };

    } catch (e) {
      console.warn('[WS] Could not connect:', e);
    }
  }, [onMessage]);

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    jobIdRef.current = null;
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => disconnect();
  }, [disconnect]);

  return { connect, disconnect };
}
