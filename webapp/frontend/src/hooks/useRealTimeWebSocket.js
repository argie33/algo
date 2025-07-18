/**
 * Real-Time WebSocket Hook for LiveData Integration
 * Integrates with deployed AWS WebSocket API Gateway and Alpaca streams
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { useAuth } from '../contexts/AuthContext';

const useRealTimeWebSocket = () => {
  const { user, isAuthenticated } = useAuth();
  const wsRef = useRef(null);
  const reconnectAttempts = useRef(0);
  const maxReconnectAttempts = 5;
  const reconnectDelay = useRef(1000);
  
  // State management
  const [connectionStatus, setConnectionStatus] = useState('disconnected');
  const [isStreaming, setIsStreaming] = useState(false);
  const [liveData, setLiveData] = useState([]);
  const [subscribedSymbols, setSubscribedSymbols] = useState(new Set());
  const [connectionStats, setConnectionStats] = useState({
    connectedAt: null,
    messagesReceived: 0,
    latency: 0,
    reconnectCount: 0
  });
  const [errors, setErrors] = useState([]);

  // Get WebSocket URL from configuration
  const getWebSocketUrl = useCallback(() => {
    // Check runtime config first (from CloudFormation outputs)
    if (window.__CONFIG__?.ALPACA_WEBSOCKET_ENDPOINT) {
      return window.__CONFIG__.ALPACA_WEBSOCKET_ENDPOINT;
    }
    
    // Check environment variables
    if (import.meta.env.VITE_ALPACA_WS_URL) {
      return import.meta.env.VITE_ALPACA_WS_URL;
    }
    
    // Fallback to expected CloudFormation format
    // This should match the output from template-alpaca-websocket.yml
    return 'wss://your-websocket-api-id.execute-api.us-east-1.amazonaws.com/dev';
  }, []);

  // Add error to list with timestamp
  const addError = useCallback((error) => {
    const errorEntry = {
      id: Date.now(),
      message: error.message || error,
      timestamp: new Date().toISOString(),
      type: error.type || 'connection'
    };
    setErrors(prev => [errorEntry, ...prev.slice(0, 9)]); // Keep last 10 errors
  }, []);

  // Clear all errors
  const clearErrors = useCallback(() => {
    setErrors([]);
  }, []);

  // Connect to WebSocket
  const connect = useCallback(() => {
    if (!isAuthenticated || !user) {
      addError({ message: 'Authentication required for WebSocket connection', type: 'auth' });
      return;
    }

    if (wsRef.current?.readyState === WebSocket.OPEN) {
      console.log('WebSocket already connected');
      return;
    }

    const wsUrl = getWebSocketUrl();
    console.log('🔌 Connecting to WebSocket:', wsUrl);

    try {
      // Include user ID in connection for backend authentication
      const fullWsUrl = `${wsUrl}?userId=${user.id || user.sub}`;
      
      wsRef.current = new WebSocket(fullWsUrl);
      setConnectionStatus('connecting');

      wsRef.current.onopen = (event) => {
        console.log('✅ WebSocket connected:', event);
        setConnectionStatus('connected');
        setIsStreaming(true);
        reconnectAttempts.current = 0;
        reconnectDelay.current = 1000;
        
        setConnectionStats(prev => ({
          ...prev,
          connectedAt: new Date().toISOString(),
          reconnectCount: prev.reconnectCount + (prev.connectedAt ? 1 : 0)
        }));

        // Send authentication message
        const authMessage = {
          action: 'authenticate',
          userId: user.id || user.sub,
          timestamp: new Date().toISOString()
        };
        
        wsRef.current.send(JSON.stringify(authMessage));
      };

      wsRef.current.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          
          // Update message count
          setConnectionStats(prev => ({
            ...prev,
            messagesReceived: prev.messagesReceived + 1,
            latency: Date.now() - new Date(message.timestamp || Date.now()).getTime()
          }));

          // Handle different message types
          switch (message.type) {
            case 'market_data':
              setLiveData(prev => {
                const updated = [...prev];
                const existingIndex = updated.findIndex(item => item.symbol === message.symbol);
                
                const newData = {
                  id: `${message.symbol}-${Date.now()}`,
                  symbol: message.symbol,
                  price: message.data.price || message.data.close,
                  change: message.data.change,
                  changePercent: message.data.changePercent,
                  volume: message.data.volume,
                  timestamp: message.data.timestamp || new Date().toISOString(),
                  dataType: message.dataType || 'quote'
                };

                if (existingIndex >= 0) {
                  updated[existingIndex] = newData;
                } else {
                  updated.unshift(newData);
                }

                // Keep last 100 updates
                return updated.slice(0, 100);
              });
              break;

            case 'subscription_status':
              console.log('📊 Subscription status:', message);
              if (message.status === 'confirmed') {
                setSubscribedSymbols(prev => new Set([...prev, message.symbol]));
              }
              break;

            case 'error':
              addError({ message: message.message, type: 'server' });
              break;

            case 'heartbeat':
              // Update latency from heartbeat
              setConnectionStats(prev => ({
                ...prev,
                latency: Date.now() - new Date(message.timestamp).getTime()
              }));
              break;

            default:
              console.log('📨 Received message:', message);
          }
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error);
          addError({ message: 'Failed to parse server message', type: 'parse' });
        }
      };

      wsRef.current.onclose = (event) => {
        console.log('❌ WebSocket closed:', event.code, event.reason);
        setConnectionStatus('disconnected');
        setIsStreaming(false);
        
        // Attempt to reconnect if not a clean close
        if (event.code !== 1000 && reconnectAttempts.current < maxReconnectAttempts) {
          setTimeout(() => {
            reconnectAttempts.current++;
            reconnectDelay.current = Math.min(reconnectDelay.current * 2, 30000);
            addError({ 
              message: `Reconnecting... (attempt ${reconnectAttempts.current}/${maxReconnectAttempts})`,
              type: 'reconnect' 
            });
            connect();
          }, reconnectDelay.current);
        } else if (reconnectAttempts.current >= maxReconnectAttempts) {
          addError({ message: 'Max reconnection attempts reached', type: 'connection' });
        }
      };

      wsRef.current.onerror = (error) => {
        console.error('WebSocket error:', error);
        addError({ message: 'WebSocket connection error', type: 'connection' });
        setConnectionStatus('error');
      };

    } catch (error) {
      console.error('Failed to create WebSocket connection:', error);
      addError({ message: 'Failed to create WebSocket connection', type: 'connection' });
      setConnectionStatus('error');
    }
  }, [isAuthenticated, user, getWebSocketUrl, addError]);

  // Disconnect from WebSocket
  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close(1000, 'Client disconnect');
      wsRef.current = null;
    }
    setConnectionStatus('disconnected');
    setIsStreaming(false);
    setSubscribedSymbols(new Set());
    setLiveData([]);
  }, []);

  // Subscribe to symbol updates
  const subscribe = useCallback((symbols) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      addError({ message: 'WebSocket not connected. Cannot subscribe to symbols.', type: 'subscription' });
      return;
    }

    const symbolArray = Array.isArray(symbols) ? symbols : [symbols];
    
    const subscribeMessage = {
      action: 'subscribe',
      symbols: symbolArray,
      dataTypes: ['quotes', 'trades'], // Subscribe to both quotes and trades
      timestamp: new Date().toISOString()
    };

    wsRef.current.send(JSON.stringify(subscribeMessage));
    
    // Update local subscription state
    setSubscribedSymbols(prev => {
      const updated = new Set(prev);
      symbolArray.forEach(symbol => updated.add(symbol.toUpperCase()));
      return updated;
    });

    console.log('📈 Subscribed to symbols:', symbolArray);
  }, [addError]);

  // Unsubscribe from symbol updates
  const unsubscribe = useCallback((symbols) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      addError({ message: 'WebSocket not connected. Cannot unsubscribe from symbols.', type: 'subscription' });
      return;
    }

    const symbolArray = Array.isArray(symbols) ? symbols : [symbols];
    
    const unsubscribeMessage = {
      action: 'unsubscribe',
      symbols: symbolArray,
      timestamp: new Date().toISOString()
    };

    wsRef.current.send(JSON.stringify(unsubscribeMessage));
    
    // Update local subscription state
    setSubscribedSymbols(prev => {
      const updated = new Set(prev);
      symbolArray.forEach(symbol => updated.delete(symbol.toUpperCase()));
      return updated;
    });

    console.log('📉 Unsubscribed from symbols:', symbolArray);
  }, [addError]);

  // Send custom message
  const sendMessage = useCallback((message) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
    } else {
      addError({ message: 'WebSocket not connected. Cannot send message.', type: 'send' });
    }
  }, [addError]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close(1000, 'Component unmount');
      }
    };
  }, []);

  return {
    // Connection state
    connectionStatus,
    isStreaming,
    isConnected: connectionStatus === 'connected',
    
    // Data
    liveData,
    subscribedSymbols: Array.from(subscribedSymbols),
    connectionStats,
    errors,
    
    // Actions
    connect,
    disconnect,
    subscribe,
    unsubscribe,
    sendMessage,
    clearErrors,
    
    // Utilities
    wsUrl: getWebSocketUrl()
  };
};

export default useRealTimeWebSocket;