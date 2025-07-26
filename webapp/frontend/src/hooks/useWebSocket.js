import { useState, useEffect, useRef, useCallback } from 'react';

/**
 * Enhanced WebSocket hook for real-time AI chat
 * 
 * Provides robust WebSocket connection management with:
 * - Automatic reconnection
 * - Connection state management
 * - Message queuing
 * - Error handling
 */
export const useWebSocket = (url, options = {}) => {
  const {
    enabled = true,
    reconnectAttempts = 5,
    reconnectInterval = 3000,
    heartbeatInterval = 30000,
    onOpen,
    onClose,
    onError,
    onMessage,
    protocols = []
  } = options;

  // State
  const [isConnected, setIsConnected] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [lastMessage, setLastMessage] = useState(null);
  const [connectionId, setConnectionId] = useState(null);
  const [error, setError] = useState(null);
  const [reconnectCount, setReconnectCount] = useState(0);

  // Refs
  const ws = useRef(null);
  const reconnectTimer = useRef(null);
  const heartbeatTimer = useRef(null);
  const messageQueue = useRef([]);
  const isManualClose = useRef(false);

  // Get WebSocket URL with authentication
  const getWebSocketUrl = useCallback(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const baseUrl = `${protocol}//${host}${url}`;
    
    // Add authentication token if available
    const token = localStorage.getItem('authToken') || sessionStorage.getItem('authToken');
    if (token) {
      return `${baseUrl}?token=${encodeURIComponent(token)}`;
    }
    
    return baseUrl;
  }, [url]);

  // Send message
  const sendMessage = useCallback((data) => {
    if (ws.current && ws.current.readyState === WebSocket.OPEN) {
      const message = typeof data === 'string' ? data : JSON.stringify(data);
      ws.current.send(message);
      return true;
    } else {
      // Queue message for when connection is restored
      messageQueue.current.push(data);
      console.warn('WebSocket not connected. Message queued.');
      return false;
    }
  }, []);

  // Send queued messages
  const sendQueuedMessages = useCallback(() => {
    while (messageQueue.current.length > 0 && ws.current?.readyState === WebSocket.OPEN) {
      const message = messageQueue.current.shift();
      sendMessage(message);
    }
  }, [sendMessage]);

  // Start heartbeat
  const startHeartbeat = useCallback(() => {
    if (heartbeatTimer.current) {
      clearInterval(heartbeatTimer.current);
    }
    
    heartbeatTimer.current = setInterval(() => {
      if (ws.current?.readyState === WebSocket.OPEN) {
        sendMessage({ type: 'ping', timestamp: Date.now() });
      }
    }, heartbeatInterval);
  }, [heartbeatInterval, sendMessage]);

  // Stop heartbeat
  const stopHeartbeat = useCallback(() => {
    if (heartbeatTimer.current) {
      clearInterval(heartbeatTimer.current);
      heartbeatTimer.current = null;
    }
  }, []);

  // Connect WebSocket
  const connect = useCallback(() => {
    if (!enabled || isConnecting || (ws.current && ws.current.readyState === WebSocket.OPEN)) {
      return;
    }

    console.log('🔌 Connecting to WebSocket:', getWebSocketUrl());
    setIsConnecting(true);
    setError(null);
    isManualClose.current = false;

    try {
      ws.current = new WebSocket(getWebSocketUrl(), protocols);

      ws.current.onopen = (event) => {
        console.log('✅ WebSocket connected');
        setIsConnected(true);
        setIsConnecting(false);
        setReconnectCount(0);
        setError(null);
        
        // Start heartbeat
        startHeartbeat();
        
        // Send queued messages
        sendQueuedMessages();
        
        if (onOpen) onOpen(event);
      };

      ws.current.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          setLastMessage({ data, timestamp: Date.now() });
          
          // Handle connection establishment
          if (data.type === 'connection_established') {
            setConnectionId(data.connectionId);
          }
          
          // Handle pong responses
          if (data.type === 'pong') {
            // Connection is alive
            return;
          }
          
          if (onMessage) onMessage(event);
        } catch (error) {
          console.error('Error parsing WebSocket message:', error);
          setLastMessage({ data: event.data, timestamp: Date.now() });
          if (onMessage) onMessage(event);
        }
      };

      ws.current.onclose = (event) => {
        console.log('🔌 WebSocket disconnected:', event.code, event.reason);
        setIsConnected(false);
        setIsConnecting(false);
        setConnectionId(null);
        
        // Stop heartbeat
        stopHeartbeat();
        
        if (onClose) onClose(event);

        // Attempt reconnection if not manual close
        if (!isManualClose.current && enabled && reconnectCount < reconnectAttempts) {
          console.log(`🔄 Reconnecting in ${reconnectInterval}ms (attempt ${reconnectCount + 1}/${reconnectAttempts})`);
          
          reconnectTimer.current = setTimeout(() => {
            setReconnectCount(prev => prev + 1);
            connect();
          }, reconnectInterval);
        } else if (reconnectCount >= reconnectAttempts) {
          console.error('❌ Max reconnection attempts reached');
          setError(new Error('Max reconnection attempts reached'));
        }
      };

      ws.current.onerror = (event) => {
        console.error('❌ WebSocket error:', event);
        setError(new Error('WebSocket connection error'));
        setIsConnecting(false);
        
        if (onError) onError(event);
      };

    } catch (error) {
      console.error('❌ Failed to create WebSocket:', error);
      setError(error);
      setIsConnecting(false);
    }
  }, [
    enabled,
    isConnecting,
    getWebSocketUrl,
    protocols,
    reconnectCount,
    reconnectAttempts,
    reconnectInterval,
    onOpen,
    onClose,
    onError,
    onMessage,
    startHeartbeat,
    stopHeartbeat,
    sendQueuedMessages
  ]);

  // Disconnect WebSocket
  const disconnect = useCallback(() => {
    isManualClose.current = true;
    
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current);
      reconnectTimer.current = null;
    }
    
    stopHeartbeat();
    
    if (ws.current) {
      ws.current.close(1000, 'Manual disconnect');
      ws.current = null;
    }
    
    setIsConnected(false);
    setIsConnecting(false);
    setConnectionId(null);
    setReconnectCount(0);
    setError(null);
  }, [stopHeartbeat]);

  // Reconnect manually
  const reconnect = useCallback(() => {
    disconnect();
    setTimeout(connect, 100);
  }, [connect, disconnect]);

  // Get connection status
  const getConnectionStatus = useCallback(() => {
    if (!ws.current) return 'disconnected';
    
    switch (ws.current.readyState) {
      case WebSocket.CONNECTING:
        return 'connecting';
      case WebSocket.OPEN:
        return 'connected';
      case WebSocket.CLOSING:
        return 'closing';
      case WebSocket.CLOSED:
        return 'disconnected';
      default:
        return 'unknown';
    }
  }, []);

  // Get connection stats
  const getStats = useCallback(() => {
    return {
      isConnected,
      isConnecting,
      connectionId,
      reconnectCount,
      queuedMessages: messageQueue.current.length,
      status: getConnectionStatus(),
      error: error?.message,
      lastMessage: lastMessage?.timestamp
    };
  }, [isConnected, isConnecting, connectionId, reconnectCount, error, lastMessage, getConnectionStatus]);

  // Effect to handle connection
  useEffect(() => {
    if (enabled) {
      connect();
    } else {
      disconnect();
    }

    // Cleanup on unmount
    return () => {
      disconnect();
    };
  }, [enabled]); // Only reconnect when enabled changes

  // Effect to handle visibility change (reconnect when tab becomes visible)
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible' && enabled && !isConnected && !isConnecting) {
        console.log('🔄 Tab became visible, attempting to reconnect...');
        connect();
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, [enabled, isConnected, isConnecting, connect]);

  // Effect to handle online/offline events
  useEffect(() => {
    const handleOnline = () => {
      if (enabled && !isConnected && !isConnecting) {
        console.log('🌐 Network restored, attempting to reconnect...');
        connect();
      }
    };

    const handleOffline = () => {
      console.log('🌐 Network lost');
      setError(new Error('Network connection lost'));
    };

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);
    
    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, [enabled, isConnected, isConnecting, connect]);

  return {
    // Connection state
    isConnected,
    isConnecting,
    connectionId,
    error,
    reconnectCount,
    
    // Connection control
    connect,
    disconnect,
    reconnect,
    
    // Messaging
    sendMessage,
    lastMessage,
    
    // Status and stats
    getConnectionStatus,
    getStats,
    
    // WebSocket instance (for advanced usage)
    ws: ws.current
  };
};

export default useWebSocket;