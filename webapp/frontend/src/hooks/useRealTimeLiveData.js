/**
 * Real-Time Live Data Hook using HTTP Polling
 * Uses actual deployed API endpoints instead of WebSocket placeholders
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { getApiConfig } from '../services/api';

const useRealTimeLiveData = () => {
  const { user, isAuthenticated } = useAuth();
  const { apiUrl } = getApiConfig();
  const intervalRef = useRef(null);
  const requestRef = useRef(null);
  
  // State management
  const [isStreaming, setIsStreaming] = useState(false);
  const [liveData, setLiveData] = useState([]);
  const [subscribedSymbols, setSubscribedSymbols] = useState(['AAPL', 'GOOGL', 'MSFT', 'TSLA']);
  const [connectionStats, setConnectionStats] = useState({
    startedAt: null,
    requestCount: 0,
    successCount: 0,
    errorCount: 0,
    lastUpdate: null,
    latency: 0
  });
  const [errors, setErrors] = useState([]);
  const [pollingInterval, setPollingInterval] = useState(5000); // 5 seconds

  // Add error to list
  const addError = useCallback((error) => {
    const errorEntry = {
      id: Date.now(),
      message: error.message || error,
      timestamp: new Date().toISOString(),
      type: error.type || 'api'
    };
    setErrors(prev => [errorEntry, ...prev.slice(0, 9)]);
  }, []);

  // Clear errors
  const clearErrors = useCallback(() => {
    setErrors([]);
  }, []);

  // Fetch live data from real API endpoints
  const fetchLiveData = useCallback(async () => {
    if (!isAuthenticated || subscribedSymbols.length === 0) {
      return;
    }

    const startTime = Date.now();
    
    try {
      setConnectionStats(prev => ({
        ...prev,
        requestCount: prev.requestCount + 1
      }));

      // Use real live data endpoint
      const response = await fetch(`${apiUrl}/api/live-data/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${user?.token || ''}`
        },
        body: JSON.stringify({
          symbols: subscribedSymbols,
          types: ['quotes', 'trades']
        })
      });

      if (!response.ok) {
        throw new Error(`API Error: ${response.status} ${response.statusText}`);
      }

      const data = await response.json();
      const latency = Date.now() - startTime;

      setConnectionStats(prev => ({
        ...prev,
        successCount: prev.successCount + 1,
        lastUpdate: new Date().toISOString(),
        latency
      }));

      // Process the response data
      if (data.success && data.data) {
        const newDataPoints = data.data.map(item => ({
          id: `${item.symbol}-${Date.now()}-${Math.random()}`,
          symbol: item.symbol,
          price: parseFloat(item.price || item.close || 0),
          change: parseFloat(item.change || 0),
          changePercent: parseFloat(item.changePercent || item.change_percent || 0),
          volume: parseInt(item.volume || 0),
          timestamp: item.timestamp || new Date().toISOString(),
          dataType: item.type || 'quote',
          high: parseFloat(item.high || 0),
          low: parseFloat(item.low || 0),
          open: parseFloat(item.open || 0)
        }));

        setLiveData(prev => {
          // Merge with existing data, keeping latest per symbol
          const symbolMap = new Map();
          
          // Add existing data
          prev.forEach(item => {
            symbolMap.set(item.symbol, item);
          });
          
          // Update with new data
          newDataPoints.forEach(item => {
            symbolMap.set(item.symbol, item);
          });
          
          // Return as array, most recent first
          return Array.from(symbolMap.values())
            .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))
            .slice(0, 100); // Keep last 100 updates
        });
      }

    } catch (error) {
      console.error('Live data fetch error:', error);
      setConnectionStats(prev => ({
        ...prev,
        errorCount: prev.errorCount + 1
      }));
      addError({
        message: `Failed to fetch live data: ${error.message}`,
        type: 'api'
      });
    }
  }, [isAuthenticated, subscribedSymbols, apiUrl, user, addError]);

  // Start streaming
  const startStreaming = useCallback(() => {
    if (!isAuthenticated) {
      addError({ message: 'Authentication required for live data', type: 'auth' });
      return;
    }

    console.log('🚀 Starting live data streaming...');
    setIsStreaming(true);
    setConnectionStats(prev => ({
      ...prev,
      startedAt: new Date().toISOString()
    }));

    // Initial fetch
    fetchLiveData();

    // Set up polling interval
    intervalRef.current = setInterval(fetchLiveData, pollingInterval);
  }, [isAuthenticated, fetchLiveData, pollingInterval, addError]);

  // Stop streaming
  const stopStreaming = useCallback(() => {
    console.log('⏹️ Stopping live data streaming...');
    setIsStreaming(false);
    
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    
    if (requestRef.current) {
      requestRef.current.abort();
      requestRef.current = null;
    }
  }, []);

  // Subscribe to symbols
  const subscribe = useCallback((symbols) => {
    const symbolArray = Array.isArray(symbols) ? symbols : [symbols];
    const upperSymbols = symbolArray.map(s => s.toUpperCase());
    
    setSubscribedSymbols(prev => {
      const newSymbols = [...new Set([...prev, ...upperSymbols])];
      console.log('📈 Subscribed to symbols:', newSymbols);
      return newSymbols;
    });
  }, []);

  // Unsubscribe from symbols
  const unsubscribe = useCallback((symbols) => {
    const symbolArray = Array.isArray(symbols) ? symbols : [symbols];
    const upperSymbols = symbolArray.map(s => s.toUpperCase());
    
    setSubscribedSymbols(prev => {
      const filtered = prev.filter(symbol => !upperSymbols.includes(symbol));
      console.log('📉 Unsubscribed from symbols. Remaining:', filtered);
      return filtered;
    });
  }, []);

  // Manual refresh
  const refresh = useCallback(() => {
    console.log('🔄 Manual refresh triggered');
    fetchLiveData();
  }, [fetchLiveData]);

  // Update polling interval
  const updatePollingInterval = useCallback((newInterval) => {
    setPollingInterval(newInterval);
    
    if (isStreaming) {
      // Restart with new interval
      stopStreaming();
      setTimeout(() => startStreaming(), 100);
    }
  }, [isStreaming, stopStreaming, startStreaming]);

  // Auto-start streaming when authenticated
  useEffect(() => {
    if (isAuthenticated && !isStreaming) {
      console.log('🔌 Auto-starting live data stream...');
      startStreaming();
    }
  }, [isAuthenticated, isStreaming, startStreaming]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopStreaming();
    };
  }, [stopStreaming]);

  // Format price helper
  const formatPrice = useCallback((price) => {
    if (!price || isNaN(price)) return 'N/A';
    return parseFloat(price).toFixed(2);
  }, []);

  // Format change percent helper
  const formatChangePercent = useCallback((changePercent) => {
    if (!changePercent || isNaN(changePercent)) return 'N/A';
    const value = parseFloat(changePercent);
    return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
  }, []);

  return {
    // State
    isStreaming,
    liveData,
    subscribedSymbols,
    connectionStats,
    errors,
    pollingInterval,
    
    // Actions
    startStreaming,
    stopStreaming,
    subscribe,
    unsubscribe,
    refresh,
    clearErrors,
    updatePollingInterval,
    
    // Utilities
    formatPrice,
    formatChangePercent,
    isConnected: isStreaming,
    connectionStatus: isStreaming ? 'streaming' : 'stopped'
  };
};

export default useRealTimeLiveData;