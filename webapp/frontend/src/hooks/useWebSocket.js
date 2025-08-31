import { useState, useRef, useEffect, useCallback } from 'react';

export const useWebSocket = (url, options = {}) => {
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState(null);
  const ws = useRef(null);
  const reconnectTimeoutId = useRef(null);
  
  const connect = useCallback(() => {
    try {
      // For now, return mock connection since WebSocket infrastructure isn't fully set up
      setIsConnected(true);
      setError(null);
      
      // Simulate connection
      ws.current = {
        readyState: 1, // WebSocket.OPEN
        send: (_data) => {
          // Mock WebSocket send
        },
        close: () => {
          setIsConnected(false);
        }
      };
      
    } catch (err) {
      setError(err);
      setIsConnected(false);
    }
  }, []);

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
    if (ws.current && ws.current.readyState === 1) {
      ws.current.send(JSON.stringify(message));
      return true;
    }
    return false;
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