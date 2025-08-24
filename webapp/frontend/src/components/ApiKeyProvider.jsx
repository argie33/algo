/**
 * API Key Provider - Centralized API key management
 */
import { createContext, useContext, useState, useEffect } from 'react';
import api from '../services/api';

// Create context
const ApiKeyContext = createContext();

// Provider component
export const ApiKeyProvider = ({ children }) => {
  const [apiKeys, setApiKeys] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Load API keys on mount
  useEffect(() => {
    loadApiKeys();
  }, []);

  const loadApiKeys = async () => {
    try {
      setLoading(true);
      const response = await api.get('/api/settings/api-keys');
      if (response.data.success) {
        setApiKeys(response.data.data || {});
      }
    } catch (err) {
      console.error('Failed to load API keys:', err);
      setError(err.message);
      // Try localStorage as fallback
      const stored = localStorage.getItem('api-keys');
      if (stored) {
        try {
          setApiKeys(JSON.parse(stored));
        } catch (parseErr) {
          console.error('Failed to parse stored API keys:', parseErr);
        }
      }
    } finally {
      setLoading(false);
    }
  };

  const setApiKey = async (provider, key) => {
    try {
      const response = await api.post('/api/settings/api-keys', {
        provider,
        key
      });
      
      if (response.data.success) {
        setApiKeys(prev => ({ ...prev, [provider]: key }));
        // Update localStorage as backup
        localStorage.setItem('api-keys', JSON.stringify({ ...apiKeys, [provider]: key }));
        return true;
      }
      return false;
    } catch (err) {
      console.error('Failed to set API key:', err);
      setError(err.message);
      return false;
    }
  };

  const removeApiKey = async (provider) => {
    try {
      const response = await api.delete(`/api/settings/api-keys/${provider}`);
      
      if (response.data.success) {
        setApiKeys(prev => {
          const updated = { ...prev };
          delete updated[provider];
          return updated;
        });
        // Update localStorage
        const updated = { ...apiKeys };
        delete updated[provider];
        localStorage.setItem('api-keys', JSON.stringify(updated));
        return true;
      }
      return false;
    } catch (err) {
      console.error('Failed to remove API key:', err);
      setError(err.message);
      return false;
    }
  };

  const hasApiKey = (provider) => {
    return !!(apiKeys && apiKeys[provider]);
  };

  const validateApiKeys = async () => {
    try {
      const response = await api.post('/api/settings/api-keys/validate');
      return response.data;
    } catch (err) {
      console.error('Failed to validate API keys:', err);
      return { success: false, error: err.message };
    }
  };

  const value = {
    apiKeys,
    loading,
    error,
    setApiKey,
    removeApiKey,
    hasApiKey,
    validateApiKeys,
    refreshApiKeys: loadApiKeys
  };

  return (
    <ApiKeyContext.Provider value={value}>
      {children}
    </ApiKeyContext.Provider>
  );
};

// Custom hook to use API keys
// eslint-disable-next-line react-refresh/only-export-components
export const useApiKeys = () => {
  const context = useContext(ApiKeyContext);
  if (!context) {
    throw new Error('useApiKeys must be used within an ApiKeyProvider');
  }
  return context;
};

export default ApiKeyProvider;