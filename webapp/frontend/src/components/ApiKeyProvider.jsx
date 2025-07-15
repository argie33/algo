/**
 * API Key Provider - Context for managing API key state across the application
 * Provides centralized API key detection, onboarding flow, and authentication integration
 */

import React, { createContext, useContext, useState, useEffect } from 'react';
import settingsService from '../services/settingsService';
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

  const loadApiKeys = async () => {
    try {
      setIsLoading(true);
      setError(null);
      
      console.log('🔑 Loading API keys from backend...');
      
      // Try to migrate localStorage keys first
      const migrationResult = await settingsService.migrateLocalStorageToBackend();
      if (migrationResult.migrated) {
        console.log('✅ Migrated API keys from localStorage');
      }
      
      // Load API keys from backend
      const backendApiKeys = await settingsService.getApiKeys();
      const formattedKeys = settingsService.formatApiKeysForFrontend(backendApiKeys);
      
      setApiKeys(formattedKeys);
      
      // Check if user has any configured API keys
      const hasAnyKeys = Object.values(formattedKeys).some(key => 
        key.enabled || key.keyId || key.apiKey
      );
      
      setHasApiKeys(hasAnyKeys);
      setNeedsOnboarding(!hasAnyKeys);
      
      console.log('✅ API keys loaded:', {
        hasAnyKeys,
        alpacaEnabled: formattedKeys.alpaca?.enabled,
        polygonEnabled: formattedKeys.polygon?.enabled,
        finnhubEnabled: formattedKeys.finnhub?.enabled
      });
      
    } catch (error) {
      console.error('❌ Error loading API keys:', error);
      setError(error.message);
      
      // Graceful degradation - check localStorage as fallback
      const localSettings = localStorage.getItem('app_settings');
      if (localSettings) {
        try {
          const parsed = JSON.parse(localSettings);
          if (parsed.apiKeys) {
            const hasLocalKeys = Object.values(parsed.apiKeys).some(key => 
              key.enabled || key.keyId || key.apiKey
            );
            setHasApiKeys(hasLocalKeys);
            setNeedsOnboarding(!hasLocalKeys);
            console.log('📱 Using localStorage fallback for API key detection');
          }
        } catch (parseError) {
          console.error('Error parsing localStorage settings:', parseError);
        }
      }
    } finally {
      setIsLoading(false);
    }
  };

  const refreshApiKeys = async () => {
    if (isAuthenticated && user) {
      await loadApiKeys();
    }
  };

  const markOnboardingComplete = (savedKeys) => {
    console.log('🎉 Onboarding completed with keys:', Object.keys(savedKeys));
    setNeedsOnboarding(false);
    setHasApiKeys(true);
    
    // Refresh API keys to get the latest state
    refreshApiKeys();
  };

  const getProviderStatus = (provider) => {
    const key = apiKeys[provider];
    if (!key) return { configured: false, enabled: false, valid: false };
    
    return {
      configured: !!(key.keyId || key.apiKey),
      enabled: key.enabled || false,
      valid: key.validationStatus === 'VALID',
      lastValidated: key.lastValidated
    };
  };

  const hasValidProvider = (provider) => {
    const status = getProviderStatus(provider);
    return status.configured && status.enabled && status.valid;
  };

  const hasAnyValidProvider = () => {
    return ['alpaca', 'polygon', 'finnhub'].some(provider => hasValidProvider(provider));
  };

  const value = {
    apiKeys,
    isLoading,
    hasApiKeys,
    needsOnboarding,
    error,
    loadApiKeys: refreshApiKeys,
    markOnboardingComplete,
    getProviderStatus,
    hasValidProvider,
    hasAnyValidProvider
  };

  return (
    <ApiKeyContext.Provider value={value}>
      {children}
    </ApiKeyContext.Provider>
  );
};

export default ApiKeyProvider;