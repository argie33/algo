/**
 * Runtime Configuration Service
 * Fetches actual AWS resource configuration from the backend API
 * This replaces hardcoded values with dynamic values from deployed infrastructure
 */

import { getApiConfig } from './api';

let cachedConfig = null;
let configPromise = null;

/**
 * Fetch runtime configuration from the backend API
 * This includes actual Cognito User Pool IDs, Client IDs, etc. from the deployed infrastructure
 */
export async function fetchRuntimeConfig() {
  // Return cached config if available
  if (cachedConfig) {
    return cachedConfig;
  }

  // Return existing promise if already in progress
  if (configPromise) {
    return configPromise;
  }

  console.log('🔧 Fetching runtime configuration from API...');

  configPromise = (async () => {
    try {
      const { apiUrl } = getApiConfig();
      const response = await fetch(`${apiUrl}/settings/runtime-config`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        },
        // Don't require authentication for runtime config
        credentials: 'omit'
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const result = await response.json();
      
      if (!result.success) {
        throw new Error(result.message || 'Failed to fetch runtime configuration');
      }

      console.log('✅ Runtime configuration fetched successfully:', {
        cognitoConfigured: !!result.config?.cognito?.userPoolId && !!result.config?.cognito?.clientId,
        environment: result.config?.environment,
        region: result.config?.cognito?.region
      });

      // Store configuration in global window object for environment.js to access
      window.__RUNTIME_CONFIG__ = result.config;
      
      cachedConfig = result.config;
      return cachedConfig;
    } catch (error) {
      console.error('❌ Failed to fetch runtime configuration:', error);
      console.warn('⚠️ Using static configuration fallback');
      
      // Clear the promise so it can be retried
      configPromise = null;
      
      // Return null to fall back to static configuration
      return null;
    }
  })();

  return configPromise;
}

/**
 * Initialize runtime configuration on app startup
 * This should be called early in the application lifecycle
 */
export async function initializeRuntimeConfig() {
  try {
    console.log('🚀 Initializing runtime configuration...');
    await fetchRuntimeConfig();
    console.log('✅ Runtime configuration initialized');
    return true;
  } catch (error) {
    console.warn('⚠️ Runtime configuration initialization failed, using fallback:', error);
    return false;
  }
}

/**
 * Get cached runtime configuration (synchronous)
 * Returns null if not yet loaded
 */
export function getRuntimeConfig() {
  return cachedConfig;
}

/**
 * Clear cached configuration (for testing or re-initialization)
 */
export function clearRuntimeConfig() {
  cachedConfig = null;
  configPromise = null;
  delete window.__RUNTIME_CONFIG__;
}

export default {
  fetchRuntimeConfig,
  initializeRuntimeConfig,
  getRuntimeConfig,
  clearRuntimeConfig
};