import { useState, useRef, useEffect, useCallback } from "react";

export const useWebSocket = (url, options = {}) => {
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState(null);
  const ws = useRef(null);
  const reconnectTimeoutId = useRef(null);

  const connect = useCallback(() => {
    try {
      // Connect to real WebSocket server - resolve URL dynamically
      let wsUrl = url;
      if (!wsUrl) {
        // Get API base URL and convert to WebSocket URL
        const apiUrl = window.__CONFIG__?.API_URL ||
                      (import.meta.env?.VITE_API_URL) ||
                      (window.location.hostname === 'localhost'
                        ? 'http://localhost:3001'
                        : window.location.origin.replace(/:\d+$/, ':3001'));
        // Convert http(s) to ws(s)
        wsUrl = apiUrl
          .replace(/^https:/, 'wss:')
          .replace(/^http:/, 'ws:') + '/ws';
      }
      if (process.env.NODE_ENV === 'development') console.log("🔗 WebSocket connecting to:", wsUrl);

      ws.current = new WebSocket(wsUrl);

      ws.current.onopen = () => {
        if (process.env.NODE_ENV === 'development') console.log("✅ WebSocket connected");
        setIsConnected(true);
        setError(null);
      };

      ws.current.onmessage = (event) => {
        if (process.env.NODE_ENV === 'development') console.log("📨 WebSocket message received:", event.data);
        if (options.onMessage) {
          options.onMessage(event.data);
        }
      };

      ws.current.onerror = (error) => {
        if (process.env.NODE_ENV === 'development') console.error("❌ WebSocket error:", error);
        setError(new Error("WebSocket connection failed"));
        setIsConnected(false);
      };

      ws.current.onclose = () => {
        if (process.env.NODE_ENV === 'development') console.log("🔌 WebSocket disconnected");
        setIsConnected(false);
      };
    } catch (err) {
      if (process.env.NODE_ENV === 'development') console.error("❌ WebSocket connection error:", err);
      setError(err);
      setIsConnected(false);
    }
  }, [url, options]);

  const disconnect = useCallback(() => {
    if (ws.current && typeof ws.current.close === 'function') {
      ws.current.close();
      ws.current = null;
    }
    setIsConnected(false);

    if (reconnectTimeoutId.current) {
      clearTimeout(reconnectTimeoutId.current);
      reconnectTimeoutId.current = null;
    }
  }, []);

  const sendMessage = useCallback((message) => {
    if (ws.current && ws.current.readyState === WebSocket.OPEN) {
      const messageStr =
        typeof message === "string" ? message : JSON.stringify(message);
      ws.current.send(messageStr);
      console.log("📤 WebSocket message sent:", messageStr);
      return true;
    } else {
      console.warn("⚠️ WebSocket not connected, cannot send message:", message);
      return false;
    }
  }, []);

  useEffect(() => {
    // Support both 'autoConnect' and 'enabled' options for backward compatibility
    const shouldConnect = options.enabled !== false && options.autoConnect !== false;
    
    if (shouldConnect) {
      connect();
    } else {
      disconnect();
    }

    return () => {
      disconnect();
    };
  }, [connect, disconnect, options.autoConnect, options.enabled]);

  return {
    isConnected,
    error,
    sendMessage,
    connect,
    disconnect,
  };
};
