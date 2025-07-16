/**
 * Settings Service - Backend API Integration
 * Handles API key management and user settings with backend persistence
 */

import api from './api';

class SettingsService {
  constructor() {
    this.baseUrl = '/api/settings';
  }

  /**
   * Get all API keys for the authenticated user
   */
  async getApiKeys() {
    try {
      console.log('📡 Fetching API keys from backend...');
      const response = await api.get(`${this.baseUrl}/api-keys`);
      
      if (response.data.success) {
        console.log('✅ Successfully fetched API keys:', response.data.data.length, 'keys');
        return response.data.data;
      } else {
        throw new Error(response.data.error || 'Failed to fetch API keys');
      }
    } catch (error) {
      console.error('❌ Error fetching API keys:', error);
      
      // Return empty array for graceful degradation
      if (error.response?.status === 404 || error.response?.status === 422) {
        console.log('📝 No API keys found or service unavailable, returning empty array');
        return [];
      }
      
      throw error;
    }
  }

  /**
   * Add a new API key
   */
  async addApiKey(apiKeyData) {
    try {
      console.log('📡 Adding new API key:', { provider: apiKeyData.provider });
      
      const payload = {
        provider: apiKeyData.provider,
        apiKey: apiKeyData.apiKey,
        apiSecret: apiKeyData.apiSecret,
        isSandbox: apiKeyData.isSandbox || true,
        description: apiKeyData.description || `${apiKeyData.provider} API key`
      };

      const response = await api.post(`${this.baseUrl}/api-keys`, payload);
      
      if (response.data.success) {
        console.log('✅ Successfully added API key:', response.data.data.id);
        return response.data.data;
      } else {
        throw new Error(response.data.error || 'Failed to add API key');
      }
    } catch (error) {
      console.error('❌ Error adding API key:', error);
      throw error;
    }
  }

  /**
   * Update an existing API key
   */
  async updateApiKey(keyId, updates) {
    try {
      console.log('📡 Updating API key:', keyId);
      
      const response = await api.put(`${this.baseUrl}/api-keys/${keyId}`, updates);
      
      if (response.data.success) {
        console.log('✅ Successfully updated API key:', keyId);
        return response.data.data;
      } else {
        throw new Error(response.data.error || 'Failed to update API key');
      }
    } catch (error) {
      console.error('❌ Error updating API key:', error);
      throw error;
    }
  }

  /**
   * Delete an API key
   */
  async deleteApiKey(keyId) {
    try {
      console.log('📡 Deleting API key:', keyId);
      
      const response = await api.delete(`${this.baseUrl}/api-keys/${keyId}`);
      
      if (response.data.success) {
        console.log('✅ Successfully deleted API key:', keyId);
        return true;
      } else {
        throw new Error(response.data.error || 'Failed to delete API key');
      }
    } catch (error) {
      console.error('❌ Error deleting API key:', error);
      throw error;
    }
  }

  /**
   * Validate an API key with the broker
   */
  async validateApiKey(keyId, provider) {
    try {
      console.log('📡 Validating API key:', keyId, 'for provider:', provider);
      
      const response = await api.post(`${this.baseUrl}/api-keys/${keyId}/validate`, {
        provider
      });
      
      if (response.data.success) {
        console.log('✅ API key validation result:', response.data.data.valid);
        return response.data.data;
      } else {
        throw new Error(response.data.error || 'Failed to validate API key');
      }
    } catch (error) {
      console.error('❌ Error validating API key:', error);
      throw error;
    }
  }

  /**
   * Get validation status for all user API keys
   */
  async getValidationStatus(provider = null) {
    try {
      console.log('📡 Getting validation status for provider:', provider || 'all');
      
      const url = provider 
        ? `${this.baseUrl}/api-keys/validation-status?provider=${provider}`
        : `${this.baseUrl}/api-keys/validation-status`;
      
      const response = await api.get(url);
      
      if (response.data.success) {
        console.log('✅ Got validation status:', response.data.data);
        return response.data.data;
      } else {
        throw new Error(response.data.error || 'Failed to get validation status');
      }
    } catch (error) {
      console.error('❌ Error getting validation status:', error);
      return { validationStatus: 'unknown', lastValidated: null };
    }
  }

  /**
   * Validate all user API keys
   */
  async validateAllApiKeys() {
    try {
      console.log('📡 Validating all API keys...');
      
      const response = await api.post(`${this.baseUrl}/api-keys/validate-all`);
      
      if (response.data.success) {
        console.log('✅ Validated all API keys:', response.data.data.validationResults);
        return response.data.data;
      } else {
        throw new Error(response.data.error || 'Failed to validate all API keys');
      }
    } catch (error) {
      console.error('❌ Error validating all API keys:', error);
      throw error;
    }
  }

  /**
   * Get API credentials for a specific provider (for real-time services)
   */
  async getProviderCredentials(provider) {
    try {
      console.log('📡 Getting credentials for provider:', provider);
      
      const response = await api.get(`${this.baseUrl}/api-keys/${provider}/credentials`);
      
      if (response.data.success) {
        console.log('✅ Got credentials for provider:', provider);
        return response.data.data;
      } else {
        throw new Error(response.data.error || 'Failed to get provider credentials');
      }
    } catch (error) {
      console.error('❌ Error getting provider credentials:', error);
      throw error;
    }
  }

  /**
   * Convert backend API keys to frontend format for compatibility
   */
  formatApiKeysForFrontend(backendApiKeys) {
    const formatted = {
      alpaca: { keyId: '', secretKey: '', paperTrading: true, enabled: false },
      polygon: { apiKey: '', enabled: false },
      finnhub: { apiKey: '', enabled: false }
    };

    if (!Array.isArray(backendApiKeys)) {
      return formatted;
    }

    backendApiKeys.forEach(key => {
      if (key.provider === 'alpaca') {
        formatted.alpaca = {
          keyId: key.masked_api_key || '',
          secretKey: '••••••••', // Never show actual secret
          paperTrading: key.is_sandbox || true,
          enabled: key.is_active || false,
          id: key.id,
          validationStatus: key.validation_status,
          lastValidated: key.last_validated
        };
      } else if (key.provider === 'polygon') {
        formatted.polygon = {
          apiKey: key.masked_api_key || '',
          enabled: key.is_active || false,
          id: key.id,
          validationStatus: key.validation_status,
          lastValidated: key.last_validated
        };
      } else if (key.provider === 'finnhub') {
        formatted.finnhub = {
          apiKey: key.masked_api_key || '',
          enabled: key.is_active || false,
          id: key.id,
          validationStatus: key.validation_status,
          lastValidated: key.last_validated
        };
      }
    });

    return formatted;
  }

  /**
   * Migrate localStorage settings to backend (one-time migration)
   */
  async migrateLocalStorageToBackend() {
    try {
      console.log('🔄 Checking for localStorage settings to migrate...');
      
      const localSettings = localStorage.getItem('app_settings');
      if (!localSettings) {
        console.log('📝 No localStorage settings found to migrate');
        return { migrated: false, reason: 'no_local_settings' };
      }

      const settings = JSON.parse(localSettings);
      if (!settings.apiKeys) {
        console.log('📝 No API keys in localStorage to migrate');
        return { migrated: false, reason: 'no_api_keys' };
      }

      const migrations = [];

      // Migrate Alpaca API key
      if (settings.apiKeys.alpaca?.keyId && settings.apiKeys.alpaca?.secretKey) {
        try {
          await this.addApiKey({
            provider: 'alpaca',
            apiKey: settings.apiKeys.alpaca.keyId,
            apiSecret: settings.apiKeys.alpaca.secretKey,
            isSandbox: settings.apiKeys.alpaca.paperTrading || true,
            description: 'Migrated from localStorage'
          });
          migrations.push('alpaca');
        } catch (error) {
          console.warn('⚠️ Failed to migrate Alpaca API key:', error.message);
        }
      }

      // Migrate Polygon API key
      if (settings.apiKeys.polygon?.apiKey) {
        try {
          await this.addApiKey({
            provider: 'polygon',
            apiKey: settings.apiKeys.polygon.apiKey,
            apiSecret: 'not_required',
            isSandbox: false,
            description: 'Migrated from localStorage'
          });
          migrations.push('polygon');
        } catch (error) {
          console.warn('⚠️ Failed to migrate Polygon API key:', error.message);
        }
      }

      // Migrate Finnhub API key
      if (settings.apiKeys.finnhub?.apiKey) {
        try {
          await this.addApiKey({
            provider: 'finnhub',
            apiKey: settings.apiKeys.finnhub.apiKey,
            apiSecret: 'not_required',
            isSandbox: false,
            description: 'Migrated from localStorage'
          });
          migrations.push('finnhub');
        } catch (error) {
          console.warn('⚠️ Failed to migrate Finnhub API key:', error.message);
        }
      }

      if (migrations.length > 0) {
        console.log('✅ Successfully migrated API keys:', migrations);
        
        // Clear localStorage after successful migration
        localStorage.removeItem('app_settings');
        console.log('🧹 Cleared localStorage after migration');
        
        return { migrated: true, keys: migrations };
      } else {
        return { migrated: false, reason: 'no_valid_keys' };
      }

    } catch (error) {
      console.error('❌ Error during localStorage migration:', error);
      return { migrated: false, reason: 'migration_error', error: error.message };
    }
  }
}

export default new SettingsService();