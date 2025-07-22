// useRealTimeData Hook
// Custom hook for managing real-time market data connections and streaming

import { useState, useEffect, useRef, useCallback } from 'react';

export const useRealTimeData = (options = {}) => {
  const {
    autoConnect = false,
    defaultSymbols = ['AAPL', 'GOOGL', 'MSFT'],
    defaultProvider = 'alpaca',
    pollInterval = 1000,
    maxDataPoints = 100
  } = options;

  // State
  const [isConnected, setIsConnected] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState({});
  const [subscriptions, setSubscriptions] = useState({});
  const [realtimeData, setRealtimeData] = useState(new Map());
  const [trades, setTrades] = useState([]);
  const [quotes, setQuotes] = useState(new Map());
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  // Refs
  const pollIntervalRef = useRef(null);
  const subscribedSymbols = useRef(new Set());

  // Check connection status
  const checkConnectionStatus = useCallback(async () => {
    try {
      const response = await fetch('/api/realtime/status');
      const result = await response.json();
      
      if (result.success) {
        setConnectionStatus(result.data);
        setIsConnected(result.data.connectedProviders.length > 0);
        return result.data;
      }
      return null;
    } catch (error) {
      console.error('Failed to check connection status:', error);
      setError('Failed to check connection status');
      return null;
    }
  }, []);

  // Connect to providers  
  const connect = useCallback(async (providers) => {
    setLoading(true);
    setError(null);
    
    try {
      const response = await fetch('/api/realtime/connect', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ providers })
      });
      
      const result = await response.json();
      
      if (result.success) {
        setIsConnected(true);
        await checkConnectionStatus();
        return result;
      } else {
        setError(result.message || 'Failed to connect to providers');
        return null;
      }
    } catch (error) {
      console.error('Connection failed:', error);
      setError('Failed to connect to real-time providers');
      return null;
    } finally {
      setLoading(false);
    }
  }, [checkConnectionStatus]);

  // Subscribe to symbols
  const subscribe = useCallback(async (symbols, providers = null) => {
    if (!isConnected) {
      setError('Not connected to any providers');
      return false;
    }

    try {
      const symbolsArray = Array.isArray(symbols) ? symbols : [symbols];
      const upperSymbols = symbolsArray.map(s => s.toUpperCase());
      
      const response = await fetch('/api/realtime/subscribe', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          symbols: upperSymbols,
          providers
        })
      });
      
      const result = await response.json();
      
      if (result.success) {
        // Track subscriptions
        upperSymbols.forEach(symbol => {
          subscribedSymbols.current.add(symbol);
        });
        
        setSubscriptions(prev => ({
          ...prev,
          ...result.results
        }));
        
        return result;
      } else {
        setError(result.message || 'Failed to subscribe to symbols');
        return null;
      }
    } catch (error) {
      console.error('Subscription failed:', error);
      setError('Failed to subscribe to symbols');
      return null;
    }
  }, [isConnected]);

  // Unsubscribe from symbols
  const unsubscribe = useCallback(async (symbols, providers = null) => {
    try {
      const symbolsArray = Array.isArray(symbols) ? symbols : [symbols];
      const upperSymbols = symbolsArray.map(s => s.toUpperCase());
      
      const response = await fetch('/api/realtime/unsubscribe', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          symbols: upperSymbols,
          providers
        })
      });
      
      const result = await response.json();
      
      if (result.success) {
        // Remove from tracking
        upperSymbols.forEach(symbol => {
          subscribedSymbols.current.delete(symbol);
        });
        
        // Clean up data
        setRealtimeData(prev => {
          const newMap = new Map(prev);
          upperSymbols.forEach(symbol => newMap.delete(symbol));
          return newMap;
        });
        
        setQuotes(prev => {
          const newMap = new Map(prev);
          upperSymbols.forEach(symbol => newMap.delete(symbol));
          return newMap;
        });
        
        return result;
      }
      return null;
    } catch (error) {
      console.error('Unsubscribe failed:', error);
      setError('Failed to unsubscribe from symbols');
      return null;
    }
  }, []);

  // Poll for real-time data
  const pollData = useCallback(async () => {
    if (!isConnected || subscribedSymbols.current.size === 0) {
      return;
    }

    try {
      const promises = Array.from(subscribedSymbols.current).map(async (symbol) => {
        const response = await fetch(`/api/realtime/data/${symbol}?count=10`);
        const result = await response.json();
        
        if (result.success && result.data) {
          return { symbol, data: result.data };
        }
        return null;
      });
      
      const results = await Promise.all(promises);
      
      results.forEach(result => {
        if (result) {
          processRealtimeData(result.data);
        }
      });
    } catch (error) {
      console.error('Failed to poll real-time data:', error);
    }
  }, [isConnected]);

  // Process incoming real-time data
  const processRealtimeData = useCallback((data) => {
    const { symbol, lastData, recentData } = data;
    
    if (lastData) {
      // Update latest data
      setRealtimeData(prev => new Map(prev.set(symbol, lastData)));
      
      // Update based on data type
      if (lastData.type === 'trade') {
        setTrades(prev => {
          const newTrades = [lastData, ...prev].slice(0, maxDataPoints);
          return newTrades;
        });
      } else if (lastData.type === 'quote') {
        setQuotes(prev => new Map(prev.set(symbol, lastData)));
      }
    }
  }, [maxDataPoints]);

  // Start streaming
  const startStreaming = useCallback(() => {
    if (!isConnected) {
      setError('Not connected to providers');
      return;
    }

    setIsStreaming(true);
    
    // Start polling
    pollIntervalRef.current = setInterval(pollData, pollInterval);
  }, [isConnected, pollData, pollInterval]);

  // Stop streaming
  const stopStreaming = useCallback(() => {
    setIsStreaming(false);
    
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
  }, []);

  // Disconnect
  const disconnect = useCallback(async () => {
    try {
      stopStreaming();
      
      const response = await fetch('/api/realtime/disconnect', {
        method: 'POST'
      });
      
      const result = await response.json();
      
      if (result.success) {
        setIsConnected(false);
        setConnectionStatus({});
        setSubscriptions({});
        subscribedSymbols.current.clear();
        setRealtimeData(new Map());
        setTrades([]);
        setQuotes(new Map());
      }
      
      return result;
    } catch (error) {
      console.error('Disconnect failed:', error);
      setError('Failed to disconnect from providers');
      return null;
    }
  }, [stopStreaming]);

  // Get data for specific symbol
  const getSymbolData = useCallback((symbol) => {
    const upperSymbol = symbol.toUpperCase();
    return {
      latest: realtimeData.get(upperSymbol),
      quote: quotes.get(upperSymbol),
      isSubscribed: subscribedSymbols.current.has(upperSymbol)
    };
  }, [realtimeData, quotes]);

  // Health check
  const healthCheck = useCallback(async () => {
    try {
      const response = await fetch('/api/realtime/health');
      const result = await response.json();
      return result;
    } catch (error) {
      console.error('Health check failed:', error);
      return { success: false, error: error.message };
    }
  }, []);

  // Auto-connect on mount if enabled
  useEffect(() => {
    if (autoConnect) {
      checkConnectionStatus().then(status => {
        if (!status || status.connectedProviders.length === 0) {
          // Auto-connect with default provider
          connect({
            [defaultProvider]: {
              keyId: 'demo-key',
              secretKey: 'demo-secret'
            }
          }).then(result => {
            if (result && defaultSymbols.length > 0) {
              subscribe(defaultSymbols);
            }
          });
        } else {
          setIsConnected(true);
          // Subscribe to default symbols if already connected
          if (defaultSymbols.length > 0) {
            subscribe(defaultSymbols);
          }
        }
      });
    }
  }, [autoConnect, checkConnectionStatus, connect, subscribe, defaultProvider, defaultSymbols]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, []);

  return {
    // State
    isConnected,
    isStreaming,
    connectionStatus,
    subscriptions,
    realtimeData,
    trades,
    quotes,
    error,
    loading,
    
    // Actions
    connect,
    disconnect,
    subscribe,
    unsubscribe,
    startStreaming,
    stopStreaming,
    checkConnectionStatus,
    getSymbolData,
    healthCheck,
    
    // Utilities
    clearError: () => setError(null),
    getSubscribedSymbols: () => Array.from(subscribedSymbols.current)
  };
};