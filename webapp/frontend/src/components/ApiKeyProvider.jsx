/**
 * API Key Provider - Centralized API key state management
 * Handles localStorage migration, backend synchronization, and real-time status
 * Production-grade implementation with comprehensive error handling and validation
 */

import React, { createContext, useContext, useState, useEffect } from 'react';
import api from '../services/api';
import { useAuth } from '../contexts/AuthContext';

const ApiKeyContext = createContext();

export const useApiKeys = () => {
  const context = useContext(ApiKeyContext);
  if (!context) {
    throw new Error('useApiKeys must be used within an ApiKeyProvider');
  }
  return context;
};

export const ApiKeyProvider = ({ children }) => {
  const { isAuthenticated, user } = useAuth();
  const [apiKeys, setApiKeys] = useState({});
  const [isLoading, setIsLoading] = useState(true);
  const [hasApiKeys, setHasApiKeys] = useState(false);
  const [needsOnboarding, setNeedsOnboarding] = useState(false);
  const [error, setError] = useState(null);
  const [hasPerformedMigration, setHasPerformedMigration] = useState(false);

  // Enhanced API key validation rules for all supported providers
  const validationRules = {
    alpaca: {
      keyId: /^[A-Z0-9]{20}$/,
      secretKey: /^[A-Za-z0-9\/\+]{40}$/,
      name: 'Alpaca Trading API',
      description: 'Paper and live trading API access',
      keyIdFormat: '20 uppercase letters and numbers',
      secretKeyFormat: '40-character base64 encoded secret',
      setupUrl: 'https://app.alpaca.markets/paper/dashboard/overview',
      testEndpoint: '/account'
    },
    polygon: {
      keyId: /^[A-Za-z0-9_]{32}$/,
      name: 'Polygon.io Market Data',
      description: 'Real-time and historical market data',
      keyIdFormat: '32-character alphanumeric API key',
      setupUrl: 'https://polygon.io/dashboard/api-keys',
      testEndpoint: '/v1/meta/symbols',
      requiresSubscription: true
    },
    finnhub: {
      keyId: /^[a-z0-9]{20}$/,
      name: 'Finnhub Financial Data',
      description: 'Financial news, earnings, and alternative data',
      keyIdFormat: '20-character lowercase alphanumeric',
      setupUrl: 'https://finnhub.io/dashboard',
      testEndpoint: '/api/v1/stock/profile2',
      freeTier: true
    },
    iex: {
      keyId: /^pk_[a-z0-9]{32}$/,
      secretKey: /^sk_[a-z0-9]{32}$/,
      name: 'IEX Cloud',
      description: 'Reliable financial data API',
      keyIdFormat: 'pk_ prefix + 32 lowercase alphanumeric',
      secretKeyFormat: 'sk_ prefix + 32 lowercase alphanumeric',
      setupUrl: 'https://iexcloud.io/console/tokens',
      testEndpoint: '/stable/stock/aapl/quote'
    },
    alpha_vantage: {
      keyId: /^[A-Z0-9]{16}$/,
      name: 'Alpha Vantage',
      description: 'Financial data and technical indicators',
      keyIdFormat: '16-character uppercase alphanumeric',
      setupUrl: 'https://www.alphavantage.co/support/#api-key',
      testEndpoint: '/query',
      freeTier: true,
      rateLimited: true
    },
    td_ameritrade: {
      keyId: /^[A-Z0-9@]{20,50}$/,
      name: 'TD Ameritrade API',
      description: 'Trading and account management (Legacy)',
      keyIdFormat: '20-50 character client ID with possible @ symbol',
      setupUrl: 'https://developer.tdameritrade.com/',
      deprecated: true,
      migrationNote: 'TD Ameritrade APIs will be discontinued. Consider migrating to Schwab.'
    }
  };

  // Load API keys when user is authenticated
  useEffect(() => {
    if (isAuthenticated && user) {
      loadApiKeys();
    } else {
      // Reset state when user is not authenticated
      setApiKeys({});
      setHasApiKeys(false);
      setNeedsOnboarding(false);
      setIsLoading(false);
      setError(null);
    }
  }, [isAuthenticated, user]);

  /**
   * Load API keys from backend with fallback to localStorage migration
   */
  const loadApiKeys = async () => {
    setIsLoading(true);
    setError(null);

    try {
      console.log('🔑 Loading API keys from backend...');
      
      // Try to get API keys from backend first
      const response = await api.get('/api/settings/api-keys');
      
      if (response.data?.success && Array.isArray(response.data.data)) {
        // Convert array response to object format
        const keysFromBackend = {};
        response.data.data.forEach(key => {
          if (key.provider && key.is_active) {
            keysFromBackend[key.provider] = {
              keyId: key.masked_api_key,
              secretKey: '***masked***', // Backend doesn't return real secret
              isActive: key.is_active,
              validationStatus: key.validation_status,
              createdAt: key.created_at,
              fromBackend: true
            };
          }
        });

        setApiKeys(keysFromBackend);
        const hasAnyKeys = Object.keys(keysFromBackend).length > 0;
        setHasApiKeys(hasAnyKeys);
        setNeedsOnboarding(!hasAnyKeys);
        
        console.log('✅ API keys loaded from backend:', Object.keys(keysFromBackend));
        
        // Perform one-time migration from localStorage if backend is empty
        if (!hasAnyKeys && !hasPerformedMigration) {
          await performLocalStorageMigration();
        }
        
      } else {
        throw new Error('Invalid backend response format');
      }

    } catch (error) {
      console.warn('⚠️ Backend API keys failed, checking localStorage:', error.message);
      
      // Fallback to localStorage if backend is unavailable
      await loadFromLocalStorage();
    }

    setIsLoading(false);
  };

  /**
   * Migrate API keys from localStorage to backend
   */
  const performLocalStorageMigration = async () => {
    try {
      console.log('🔄 Checking for localStorage API keys to migrate...');
      
      const localKeys = {};
      const providers = ['alpaca', 'td_ameritrade'];
      
      // Check for keys in localStorage
      providers.forEach(provider => {
        const keyId = localStorage.getItem(`${provider}_key_id`);
        const secretKey = localStorage.getItem(`${provider}_secret_key`);
        
        if (keyId && (secretKey || provider !== 'alpaca')) {
          localKeys[provider] = { keyId, secretKey };
        }
      });

      if (Object.keys(localKeys).length > 0) {
        console.log('📦 Found localStorage keys to migrate:', Object.keys(localKeys));
        
        // Save each key to backend
        for (const [provider, keys] of Object.entries(localKeys)) {
          await saveApiKeyToBackend(provider, keys.keyId, keys.secretKey);
        }
        
        // Clear localStorage after successful migration
        providers.forEach(provider => {
          localStorage.removeItem(`${provider}_key_id`);
          localStorage.removeItem(`${provider}_secret_key`);
        });
        
        console.log('✅ Successfully migrated API keys from localStorage to backend');
        
        // Reload from backend to get the updated keys
        await loadApiKeys();
      }
      
      setHasPerformedMigration(true);
      
    } catch (error) {
      console.error('❌ Migration from localStorage failed:', error);
    }
  };

  /**
   * Load API keys from localStorage (fallback)
   */
  const loadFromLocalStorage = async () => {
    try {
      const localKeys = {};
      const providers = ['alpaca', 'td_ameritrade'];
      
      providers.forEach(provider => {
        const keyId = localStorage.getItem(`${provider}_key_id`);
        const secretKey = localStorage.getItem(`${provider}_secret_key`);
        
        if (keyId && (secretKey || provider !== 'alpaca')) {
          localKeys[provider] = {
            keyId,
            secretKey,
            isActive: true,
            validationStatus: 'unknown',
            fromBackend: false
          };
        }
      });

      setApiKeys(localKeys);
      const hasAnyKeys = Object.keys(localKeys).length > 0;
      setHasApiKeys(hasAnyKeys);
      setNeedsOnboarding(!hasAnyKeys);
      
      console.log('📱 Loaded from localStorage:', Object.keys(localKeys));
      
    } catch (error) {
      console.error('❌ Failed to load from localStorage:', error);
      setError('Failed to load API keys');
    }
  };

  /**
   * Save API key to backend
   */
  const saveApiKeyToBackend = async (provider, keyId, secretKey = null) => {
    try {
      console.log(`💾 Saving ${provider} API key to backend...`);
      
      const payload = {
        provider,
        keyId,
        secretKey: secretKey || undefined
      };

      const response = await api.post('/api/settings/api-keys', payload);
      
      if (response.data?.success) {
        console.log(`✅ Successfully saved ${provider} API key to backend`);
        return response.data;
      } else {
        throw new Error(response.data?.message || 'Failed to save API key');
      }
      
    } catch (error) {
      console.error(`❌ Failed to save ${provider} API key:`, error);
      throw error;
    }
  };

  /**
   * Validate API key format
   */
  const validateApiKey = (provider, keyId, secretKey = null) => {
    const rules = validationRules[provider];
    if (!rules) {
      return { valid: false, error: `Unknown provider: ${provider}` };
    }

    // Validate key ID format
    if (!rules.keyId.test(keyId)) {
      return { 
        valid: false, 
        error: `Invalid ${rules.name} key format. Please check your key.` 
      };
    }

    // Validate secret key for providers that require it
    if (provider === 'alpaca' && secretKey && !rules.secretKey.test(secretKey)) {
      return { 
        valid: false, 
        error: `Invalid ${rules.name} secret format. Please check your secret.` 
      };
    }

    return { valid: true };
  };

  /**
   * Save API key (with validation and backend sync)
   */
  const saveApiKey = async (provider, keyId, secretKey = null) => {
    try {
      setError(null);
      
      // Validate format first
      const validation = validateApiKey(provider, keyId, secretKey);
      if (!validation.valid) {
        throw new Error(validation.error);
      }

      // Save to backend first
      await saveApiKeyToBackend(provider, keyId, secretKey);
      
      // Update local state
      setApiKeys(prev => ({
        ...prev,
        [provider]: {
          keyId,
          secretKey: secretKey ? '***masked***' : undefined,
          isActive: true,
          validationStatus: 'pending',
          fromBackend: true,
          createdAt: new Date().toISOString()
        }
      }));
      
      // Check if onboarding is complete
      setHasApiKeys(true);
      setNeedsOnboarding(false);
      
      console.log(`✅ API key saved for ${provider}`);
      return true;
      
    } catch (error) {
      console.error(`❌ Failed to save API key for ${provider}:`, error);
      setError(error.message);
      throw error;
    }
  };

  /**
   * Remove API key
   */
  const removeApiKey = async (provider) => {
    try {
      setError(null);
      
      // Remove from backend
      await api.delete(`/api/settings/api-keys/${provider}`);
      
      // Update local state
      setApiKeys(prev => {
        const updated = { ...prev };
        delete updated[provider];
        return updated;
      });
      
      const remainingKeys = Object.keys(apiKeys).filter(p => p !== provider);
      setHasApiKeys(remainingKeys.length > 0);
      setNeedsOnboarding(remainingKeys.length === 0);
      
      console.log(`✅ API key removed for ${provider}`);
      return true;
      
    } catch (error) {
      console.error(`❌ Failed to remove API key for ${provider}:`, error);
      setError(error.message);
      throw error;
    }
  };

  const refreshApiKeys = async () => {
    if (isAuthenticated && user) {
      await loadApiKeys();
    }
  };

  const markOnboardingComplete = (savedKeys = {}) => {
    setNeedsOnboarding(false);
    setHasApiKeys(true);
    console.log('🎉 API key onboarding marked as complete');
    // Refresh to get the latest backend state
    refreshApiKeys();
  };

  /**
   * Check if specific provider is configured and valid
   */
  const hasValidProvider = (provider) => {
    const key = apiKeys[provider];
    return key && key.isActive && key.validationStatus !== 'invalid';
  };

  /**
   * Check if any supported provider is configured
   */
  const hasAnyValidProvider = () => {
    return ['alpaca', 'td_ameritrade'].some(provider => hasValidProvider(provider));
  };

  /**
   * Get API key for specific provider (for backend requests)
   */
  const getApiKey = (provider) => {
    return apiKeys[provider];
  };

  /**
   * Get all active providers
   */
  const getActiveProviders = () => {
    return Object.keys(apiKeys).filter(provider => 
      apiKeys[provider]?.isActive
    );
  };

  const value = {
    apiKeys,
    isLoading,
    hasApiKeys,
    needsOnboarding,
    error,
    loadApiKeys: refreshApiKeys,
    saveApiKey,
    removeApiKey,
    markOnboardingComplete,
    hasValidProvider,
    hasAnyValidProvider,
    getApiKey,
    getActiveProviders,
    validateApiKey
  };

  return (
    <ApiKeyContext.Provider value={value}>
      {children}
    </ApiKeyContext.Provider>
  );
};

export default ApiKeyProvider;