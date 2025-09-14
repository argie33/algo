import { useState, useRef, useEffect, useCallback } from 'react';

export const useWebSocket = (url, options = {}) => {
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState(null);
  const ws = useRef(null);
  const reconnectTimeoutId = useRef(null);
  
  const connect = useCallback(() => {
    try {
      // Connect to real WebSocket server
      const wsUrl = url || 'ws://localhost:3001/ws';
      console.log('🔗 WebSocket connecting to:', wsUrl);
      
      ws.current = new WebSocket(wsUrl);
      
      ws.current.onopen = () => {
        console.log('✅ WebSocket connected');
        setIsConnected(true);
        setError(null);
      };
      
      ws.current.onmessage = (event) => {
        console.log('📨 WebSocket message received:', event.data);
        if (options.onMessage) {
          options.onMessage(event.data);
        }
      };
      
      ws.current.onerror = (error) => {
        console.error('❌ WebSocket error:', error);
        setError(new Error('WebSocket connection failed'));
        setIsConnected(false);
      };
      
      ws.current.onclose = () => {
        console.log('🔌 WebSocket disconnected');
        setIsConnected(false);
      };
      
    } catch (err) {
      console.error('❌ WebSocket connection error:', err);
      setError(err);
      setIsConnected(false);
    }
  }, [url, options]);

  const disconnect = useCallback(() => {
    if (ws.current) {
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
      const messageStr = typeof message === 'string' ? message : JSON.stringify(message);
      ws.current.send(messageStr);
      console.log('📤 WebSocket message sent:', messageStr);
      return true;
    } else {
      console.warn('⚠️ WebSocket not connected, cannot send message:', message);
      return false;
    }
  }, []);

  useEffect(() => {
    if (options.autoConnect !== false) {
      connect();
    }

    return () => {
      disconnect();
    };
  }, [connect, disconnect, options.autoConnect]);

  return {
    isConnected,
    error,
    sendMessage,
    connect,
    disconnect
  };
};