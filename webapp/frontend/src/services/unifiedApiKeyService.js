/**
 * Unified API Key Service - Frontend
 * Simplified, reliable API key management client
 * Single endpoint for all API key operations
 */

import apiWrapper from './apiWrapper';
import { initializeApi } from './api';

class UnifiedApiKeyService {
  constructor() {
    this.cache = new Map();
    this.cacheTTL = 5 * 60 * 1000; // 5 minutes
  }

  /**
   * Get user's API keys
   */
  async getApiKeys() {
    return apiWrapper.execute('getApiKeys', async () => {
      const response = await initializeApi().get('/api/api-keys');
      return response.data;
    }, {
      context: { operation: 'getApiKeys' },
      successMessage: 'API keys loaded successfully',
      errorMessage: 'Failed to load API keys',
      handleErrors: {
        401: () => {
          console.warn('Authentication required for API keys');
          return { success: true, data: [], count: 0 };
        },
        500: () => {
          console.warn('API key service temporarily unavailable');
          return { success: true, data: [], count: 0, message: 'Service temporarily unavailable' };
        }
      }
    });
  }

  /**
   * Add Alpaca API key
   */
  async addApiKey(apiKey, secretKey, isSandbox = true) {
    return apiWrapper.execute('addApiKey', async () => {
      // Client-side validation
      if (!apiKey || !secretKey) {
        throw new Error('API key and secret are required');
      }

      if (!apiKey.startsWith('PK') || apiKey.length < 20) {
        throw new Error('Invalid Alpaca API key format (must start with PK and be at least 20 characters)');
      }

      if (secretKey.length < 20 || secretKey.length > 80) {
        throw new Error('Alpaca API secret must be 20-80 characters long');
      }

      const response = await initializeApi().post('/api/api-keys', {
        apiKey,
        secretKey,
        isSandbox
      });

      // Clear cache on successful add
      this.clearCache();
      
      return response.data;
    }, {
      context: { 
        operation: 'addApiKey',
        provider: 'alpaca'
      },
      successMessage: 'API key added successfully',
      errorMessage: 'Failed to add API key'
    });
  }

  /**
   * Remove API key
   */
  async removeApiKey() {
    return apiWrapper.execute('removeApiKey', async () => {
      const response = await initializeApi().delete('/api/api-keys');
      
      // Clear cache on successful removal
      this.clearCache();
      
      return response.data;
    }, {
      context: { operation: 'removeApiKey' },
      successMessage: 'API key removed successfully',
      errorMessage: 'Failed to remove API key'
    });
  }

  /**
   * Check API key status
   */
  async getApiKeyStatus() {
    return apiWrapper.execute('getApiKeyStatus', async () => {
      const response = await initializeApi().get('/api/api-keys/status');
      return response.data;
    }, {
      context: { operation: 'getApiKeyStatus' },
      errorMessage: 'Failed to check API key status',
      handleErrors: {
        401: () => ({ success: true, hasApiKey: false, message: 'Authentication required' }),
        500: () => ({ success: true, hasApiKey: false, message: 'Service temporarily unavailable' })
      }
    });
  }

  /**
   * Get cached API keys (for performance)
   */
  async getCachedApiKeys() {
    const cacheKey = 'apiKeys';
    const cached = this.cache.get(cacheKey);
    
    if (cached && Date.now() - cached.timestamp < this.cacheTTL) {
      console.log('📋 Using cached API keys');
      return cached.data;
    }

    const result = await this.getApiKeys();
    
    // Cache successful results
    if (result.success) {
      this.cache.set(cacheKey, {
        data: result,
        timestamp: Date.now()
      });
    }

    return result;
  }

  /**
   * Clear cache
   */
  clearCache() {
    this.cache.clear();
    console.log('🗑️ API key cache cleared');
  }

  /**
   * Validate API key format (client-side)
   */
  validateApiKey(apiKey) {
    const errors = [];

    if (!apiKey) {
      errors.push('API key is required');
    } else {
      if (!apiKey.startsWith('PK')) {
        errors.push('Alpaca API key must start with "PK"');
      }
      if (apiKey.length < 20) {
        errors.push('API key must be at least 20 characters');
      }
      if (!/^[A-Za-z0-9]+$/.test(apiKey)) {
        errors.push('API key must contain only letters and numbers');
      }
    }

    return {
      isValid: errors.length === 0,
      errors
    };
  }

  /**
   * Validate API secret format (client-side)
   */
  validateApiSecret(secret) {
    const errors = [];

    if (!secret) {
      errors.push('API secret is required');
    } else {
      if (secret.length < 20) {
        errors.push('API secret must be at least 20 characters');
      }
      if (secret.length > 80) {
        errors.push('API secret must be no more than 80 characters');
      }
      if (!/^[A-Za-z0-9\/+=]+$/.test(secret)) {
        errors.push('API secret contains invalid characters (only alphanumeric and /+= allowed)');
      }
    }

    return {
      isValid: errors.length === 0,
      errors
    };
  }

  /**
   * Validate both API key and secret
   */
  validateCredentials(apiKey, secret) {
    const keyValidation = this.validateApiKey(apiKey);
    const secretValidation = this.validateApiSecret(secret);

    return {
      isValid: keyValidation.isValid && secretValidation.isValid,
      errors: [...keyValidation.errors, ...secretValidation.errors]
    };
  }
}

// Export singleton instance
export default new UnifiedApiKeyService();