// Enhanced Portfolio Hook with API Key Integration
// Handles portfolio data fetching with proper API key validation and fallbacks

import { useState, useEffect, useCallback } from 'react';
import { getPortfolioData, importPortfolioFromBroker, getApiKeys, testApiConnection } from '../services/api';
import { useAuth } from '../contexts/AuthContext';

const usePortfolioWithApiKeys = (autoRefresh = true, refreshInterval = 300000) => {
  const { user } = useAuth();
  const [portfolioData, setPortfolioData] = useState(null);
  const [apiKeys, setApiKeys] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [dataSource, setDataSource] = useState('unknown'); // 'live', 'demo', 'cached', 'unknown'
  const [lastUpdate, setLastUpdate] = useState(null);
  const [apiKeyStatus, setApiKeyStatus] = useState({
    hasKeys: false,
    connectedBrokers: [],
    lastChecked: null
  });

  // Check API key status
  const checkApiKeys = useCallback(async () => {
    try {
      const keys = await getApiKeys();
      const activeKeys = keys.filter(key => key.isActive);
      setApiKeys(activeKeys);
      
      // Test connections for active keys
      const connectionTests = await Promise.allSettled(
        activeKeys.map(async (key) => {
          try {
            const result = await testApiConnection(key.provider, key.id);
            return { provider: key.provider, connected: result.success, error: null };
          } catch (err) {
            return { provider: key.provider, connected: false, error: err.message };
          }
        })
      );

      const connectedBrokers = connectionTests
        .filter(test => test.status === 'fulfilled' && test.value.connected)
        .map(test => test.value.provider);

      setApiKeyStatus({
        hasKeys: activeKeys.length > 0,
        connectedBrokers,
        lastChecked: new Date().toISOString()
      });

      return { hasKeys: activeKeys.length > 0, connectedBrokers };
    } catch (err) {
      console.warn('Failed to check API keys:', err);
      setApiKeyStatus({
        hasKeys: false,
        connectedBrokers: [],
        lastChecked: new Date().toISOString()
      });
      return { hasKeys: false, connectedBrokers: [] };
    }
  }, []);

  // Fetch portfolio data with API key awareness
  const fetchPortfolioData = useCallback(async (forceRefresh = false) => {
    if (!user) return;

    try {
      setLoading(true);
      setError(null);

      // Check API key status first
      const { hasKeys, connectedBrokers } = await checkApiKeys();

      let data = null;
      let source = 'demo';

      if (hasKeys && connectedBrokers.length > 0) {
        try {
          // Try to get live data from connected brokers
          data = await getPortfolioData({ 
            source: 'live', 
            forceRefresh,
            brokers: connectedBrokers 
          });
          source = 'live';
        } catch (apiError) {
          console.warn('Live data fetch failed, falling back to cached/demo data:', apiError);
          
          // Specific error handling for API key issues
          if (apiError.response?.status === 401) {
            setError('API keys need to be reconfigured. Please check your broker API keys in Settings.');
            source = 'demo';
          } else if (apiError.response?.status === 403) {
            setError('API key permissions insufficient. Please check your broker API key permissions.');
            source = 'demo';
          } else {
            // Try cached data
            try {
              data = await getPortfolioData({ source: 'cached' });
              source = 'cached';
            } catch (cacheError) {
              // Final fallback to demo data
              data = await getPortfolioData({ source: 'demo' });
              source = 'demo';
            }
          }
        }
      } else {
        // No API keys configured, use demo data
        data = await getPortfolioData({ source: 'demo' });
        source = 'demo';
      }

      setPortfolioData(data);
      setDataSource(source);
      setLastUpdate(new Date().toISOString());

    } catch (err) {
      console.error('Portfolio data fetch failed:', err);
      setError(err.message);
      setDataSource('error');
    } finally {
      setLoading(false);
    }
  }, [user, checkApiKeys]);

  // Import portfolio from broker
  const importFromBroker = useCallback(async (broker, options = {}) => {
    try {
      setLoading(true);
      setError(null);

      // Check if broker API key is available
      const brokerKey = apiKeys.find(key => key.provider === broker && key.isActive);
      if (!brokerKey) {
        throw new Error(`${broker} API key not configured. Please set up your API keys in Settings.`);
      }

      const result = await importPortfolioFromBroker(broker, {
        apiKeyId: brokerKey.id,
        ...options
      });

      if (result.success) {
        // Refresh portfolio data after successful import
        await fetchPortfolioData(true);
        return { success: true, message: 'Portfolio imported successfully' };
      } else {
        throw new Error(result.error || 'Import failed');
      }
    } catch (err) {
      setError(err.message);
      return { success: false, error: err.message };
    } finally {
      setLoading(false);
    }
  }, [apiKeys, fetchPortfolioData]);

  // Refresh data
  const refreshData = useCallback(() => {
    return fetchPortfolioData(true);
  }, [fetchPortfolioData]);

  // Initial data load
  useEffect(() => {
    fetchPortfolioData();
  }, [fetchPortfolioData]);

  // Auto-refresh if enabled
  useEffect(() => {
    if (!autoRefresh || !user) return;

    const interval = setInterval(() => {
      fetchPortfolioData();
    }, refreshInterval);

    return () => clearInterval(interval);
  }, [autoRefresh, refreshInterval, fetchPortfolioData, user]);

  return {
    // Data
    portfolioData,
    apiKeys,
    dataSource,
    lastUpdate,
    apiKeyStatus,
    
    // State
    loading,
    error,
    
    // Actions
    refreshData,
    importFromBroker,
    checkApiKeys,
    
    // Computed values
    hasLiveData: dataSource === 'live',
    hasApiKeys: apiKeyStatus.hasKeys,
    connectedBrokers: apiKeyStatus.connectedBrokers,
    needsApiKeySetup: !apiKeyStatus.hasKeys && dataSource === 'demo'
  };
};

export default usePortfolioWithApiKeys;