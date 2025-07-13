import { getApiConfig } from './api';

class ApiKeyService {
  constructor() {
    this.apiConfig = getApiConfig();
  }

  // Get all API keys for the current user
  async getApiKeys() {
    try {
      const token = localStorage.getItem('accessToken') || localStorage.getItem('authToken') || localStorage.getItem('token');
      const response = await fetch(`${this.apiConfig.apiUrl}/api/settings/api-keys`, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      return data.success ? data.apiKeys : [];
    } catch (error) {
      console.error('Error fetching API keys:', error);
      return [];
    }
  }

  // Get API key for a specific provider
  async getApiKeyForProvider(provider) {
    try {
      const apiKeys = await this.getApiKeys();
      return apiKeys.find(key => key.provider === provider && key.isActive);
    } catch (error) {
      console.error(`Error getting API key for ${provider}:`, error);
      return null;
    }
  }

  // Test API key connection and get decrypted credentials
  async testAndGetApiKey(keyId) {
    try {
      const token = localStorage.getItem('accessToken') || localStorage.getItem('authToken') || localStorage.getItem('token');
      const response = await fetch(`${this.apiConfig.apiUrl}/api/settings/test-connection/${keyId}`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      return data.success ? data.connection : null;
    } catch (error) {
      console.error('Error testing API key connection:', error);
      return null;
    }
  }

  // Get active Alpaca API key
  async getAlpacaApiKey() {
    try {
      const alpacaKey = await this.getApiKeyForProvider('alpaca');
      if (!alpacaKey) {
        throw new Error('No active Alpaca API key found');
      }
      return alpacaKey;
    } catch (error) {
      console.error('Error getting Alpaca API key:', error);
      return null;
    }
  }

  // Get active TD Ameritrade API key
  async getTdAmeritradeApiKey() {
    try {
      const tdKey = await this.getApiKeyForProvider('td_ameritrade');
      if (!tdKey) {
        throw new Error('No active TD Ameritrade API key found');
      }
      return tdKey;
    } catch (error) {
      console.error('Error getting TD Ameritrade API key:', error);
      return null;
    }
  }

  // Check if provider has active API key
  async hasActiveApiKey(provider) {
    try {
      const apiKey = await this.getApiKeyForProvider(provider);
      return !!apiKey;
    } catch (error) {
      console.error(`Error checking API key for ${provider}:`, error);
      return false;
    }
  }

  // Get all active providers
  async getActiveProviders() {
    try {
      const apiKeys = await this.getApiKeys();
      return apiKeys
        .filter(key => key.isActive)
        .map(key => key.provider);
    } catch (error) {
      console.error('Error getting active providers:', error);
      return [];
    }
  }

  // Get decrypted API credentials for a provider
  async getDecryptedCredentials(provider) {
    try {
      // Check if user is authenticated first - use same token logic as API service
      let token = null;
      
      // Check if we're in browser context
      if (typeof window !== 'undefined') {
        // Try various storage locations for auth token (same as api.js)
        token = localStorage.getItem('authToken') || 
               sessionStorage.getItem('authToken') ||
               localStorage.getItem('accessToken') ||
               sessionStorage.getItem('accessToken') ||
               localStorage.getItem('token'); // Fallback to old key
      }
      
      if (!token) {
        console.warn(`No authentication token found - skipping ${provider} credential retrieval`);
        return null;
      }

      const response = await fetch(`${this.apiConfig.apiUrl}/api/settings/api-keys/${provider}/credentials`, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) {
        if (response.status === 401) {
          console.warn(`Authentication failed for ${provider} credentials - user may need to log in`);
          return null;
        }
        if (response.status === 404) {
          console.warn(`No active ${provider} API key found`);
          return null;
        }
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      return data.success ? data.credentials : null;
    } catch (error) {
      console.error(`Error getting decrypted credentials for ${provider}:`, error);
      return null;
    }
  }

  // Get decrypted Alpaca credentials
  async getAlpacaCredentials() {
    return this.getDecryptedCredentials('alpaca');
  }
}

export default new ApiKeyService();