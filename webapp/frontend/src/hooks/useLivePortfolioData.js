// Custom hook for live portfolio data integration
import { useState, useEffect, useCallback, useRef } from 'react';
import liveDataService from '../services/liveDataService';

export const useLivePortfolioData = (userId, apiKeyId, initialData = null) => {
  const [portfolioData, setPortfolioData] = useState(initialData);
  const [isLiveConnected, setIsLiveConnected] = useState(false);
  const [liveDataError, setLiveDataError] = useState(null);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [metrics, setMetrics] = useState({
    messagesReceived: 0,
    avgLatency: 0,
    connectionUptime: 0
  });
  
  // Refs to track subscription state
  const subscriptionRef = useRef(null);
  const isSubscribedRef = useRef(false);
  
  // Connection status handlers
  const handleConnectionStatus = useCallback((connected) => {
    setIsLiveConnected(connected);
    if (connected) {
      setLiveDataError(null);
      console.log('🟢 Live data connection established');
    } else {
      console.log('🔴 Live data connection lost');
    }
  }, []);

  // Portfolio data update handler
  const handlePortfolioUpdate = useCallback((update) => {
    console.log('📊 Portfolio live data update:', update);
    
    setLastUpdate(new Date());
    setLiveDataError(null);
    
    switch (update.type) {
      case 'portfolio_update':
        setPortfolioData(prevData => ({
          ...prevData,
          ...update.data,
          lastUpdated: new Date().toISOString(),
          dataSource: 'live'
        }));
        break;
        
      case 'holdings_update':
        setPortfolioData(prevData => ({
          ...prevData,
          holdings: update.data,
          lastUpdated: new Date().toISOString(),
          dataSource: 'live'
        }));
        break;
        
      case 'position_update':
        setPortfolioData(prevData => {
          if (!prevData?.holdings) return prevData;
          
          const updatedHoldings = prevData.holdings.map(holding => 
            holding.symbol === update.data.symbol ? {
              ...holding,
              ...update.data,
              lastUpdated: new Date().toISOString()
            } : holding
          );
          
          return {
            ...prevData,
            holdings: updatedHoldings,
            lastUpdated: new Date().toISOString(),
            dataSource: 'live'
          };
        });
        break;
        
      default:
        console.warn('Unknown portfolio update type:', update.type);
    }
  }, []);

  // Error handler
  const handleError = useCallback((error) => {
    console.error('❌ Live data error:', error);
    setLiveDataError(error);
  }, []);

  // Subscribe to live data
  const subscribe = useCallback(() => {
    if (!userId || !apiKeyId || isSubscribedRef.current) {
      return;
    }

    console.log('📊 Subscribing to live portfolio data...');
    
    try {
      // Subscribe to portfolio updates
      liveDataService.subscribeToPortfolio(userId, apiKeyId, handlePortfolioUpdate);
      subscriptionRef.current = { userId, apiKeyId };
      isSubscribedRef.current = true;
      
      console.log('✅ Successfully subscribed to live portfolio data');
    } catch (error) {
      console.error('❌ Failed to subscribe to live portfolio data:', error);
      setLiveDataError(error);
    }
  }, [userId, apiKeyId, handlePortfolioUpdate]);

  // Unsubscribe from live data
  const unsubscribe = useCallback(() => {
    if (!subscriptionRef.current || !isSubscribedRef.current) {
      return;
    }

    console.log('📊 Unsubscribing from live portfolio data...');
    
    try {
      liveDataService.unsubscribeFromPortfolio(
        subscriptionRef.current.userId,
        subscriptionRef.current.apiKeyId
      );
      subscriptionRef.current = null;
      isSubscribedRef.current = false;
      
      console.log('✅ Successfully unsubscribed from live portfolio data');
    } catch (error) {
      console.error('❌ Failed to unsubscribe from live portfolio data:', error);
    }
  }, []);

  // Connect to live data service
  const connectToLiveData = useCallback(async () => {
    try {
      if (!liveDataService.isConnected()) {
        console.log('🔗 Connecting to live data service...');
        await liveDataService.connect(userId);
      }
      
      // Subscribe to connection events
      liveDataService.on('connected', () => handleConnectionStatus(true));
      liveDataService.on('disconnected', () => handleConnectionStatus(false));
      liveDataService.on('error', handleError);
      
      // Subscribe to portfolio data
      subscribe();
      
    } catch (error) {
      console.error('❌ Failed to connect to live data service:', error);
      setLiveDataError(error);
    }
  }, [userId, subscribe, handleConnectionStatus, handleError]);

  // Disconnect from live data service
  const disconnectFromLiveData = useCallback(() => {
    console.log('🔌 Disconnecting from live data service...');
    
    unsubscribe();
    
    // Remove event listeners
    liveDataService.off('connected', handleConnectionStatus);
    liveDataService.off('disconnected', handleConnectionStatus);
    liveDataService.off('error', handleError);
    
    setIsLiveConnected(false);
    setLiveDataError(null);
  }, [unsubscribe, handleConnectionStatus, handleError]);

  // Update metrics
  const updateMetrics = useCallback(() => {
    const serviceMetrics = liveDataService.getMetrics();
    setMetrics({
      messagesReceived: serviceMetrics.messagesReceived,
      avgLatency: Math.round(serviceMetrics.avgLatency),
      connectionUptime: serviceMetrics.connectionUptime
    });
  }, []);

  // Effect to handle connection and subscription
  useEffect(() => {
    if (userId && apiKeyId) {
      connectToLiveData();
    }

    return () => {
      disconnectFromLiveData();
    };
  }, [userId, apiKeyId, connectToLiveData, disconnectFromLiveData]);

  // Effect to update metrics periodically
  useEffect(() => {
    const metricsInterval = setInterval(updateMetrics, 5000);
    return () => clearInterval(metricsInterval);
  }, [updateMetrics]);

  // Manual refresh function
  const refreshData = useCallback(() => {
    if (isSubscribedRef.current) {
      // Send refresh request to live data service
      liveDataService.sendMessage({
        action: 'refresh',
        channel: 'portfolio',
        userId: userId,
        apiKeyId: apiKeyId
      });
    }
  }, [userId, apiKeyId]);

  // Toggle live data connection
  const toggleLiveData = useCallback(() => {
    if (isLiveConnected) {
      disconnectFromLiveData();
    } else {
      connectToLiveData();
    }
  }, [isLiveConnected, connectToLiveData, disconnectFromLiveData]);

  return {
    // Data
    portfolioData,
    setPortfolioData,
    
    // Connection state
    isLiveConnected,
    liveDataError,
    lastUpdate,
    metrics,
    
    // Actions
    refreshData,
    toggleLiveData,
    subscribe,
    unsubscribe,
    
    // Utility
    isSubscribed: isSubscribedRef.current,
    subscriptionInfo: subscriptionRef.current
  };
};

export default useLivePortfolioData;