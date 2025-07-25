/**
 * Configuration Service
 * Handles loading and validation of configuration from various sources
 * with proper fallbacks and error handling
 */

class ConfigurationService {
  constructor() {
    this.configCache = null;
    this.initialized = false;
  }

  /**
   * Initialize configuration from all available sources
   * Priority: CloudFormation > Environment Variables > Defaults
   */
  async initialize() {
    if (this.initialized && this.configCache) {
      return this.configCache;
    }

    try {
      // Load from CloudFormation config if available (now async)
      const cloudFormationConfig = await this.loadCloudFormationConfig();
      
      // Load from window.__CONFIG__ if available
      const windowConfig = this.loadWindowConfig();
      
      // Load from environment variables
      const envConfig = this.loadEnvironmentConfig();
      
      // Merge configurations with proper priority
      this.configCache = this.mergeConfigurations(
        cloudFormationConfig,
        windowConfig,
        envConfig,
        this.getDefaultConfig()
      );
      
      // Validate the final configuration
      this.validateConfiguration(this.configCache);
      
      this.initialized = true;
      return this.configCache;
      
    } catch (error) {
      console.error('❌ Configuration initialization failed:', error);
      
      // Return safe fallback configuration with enhanced error context
      console.warn('🔧 Using safety fallback configuration due to initialization error');
      console.warn('💡 The app will continue to work with CloudFormation config and default settings');
      this.configCache = this.getSafetyFallbackConfig();
      this.initialized = true;
      return this.configCache;
    }
  }

  /**
   * Load CloudFormation configuration if available
   */
  async loadCloudFormationConfig() {
    if (typeof window === 'undefined') return {};
    
    // First try window.__CLOUDFORMATION_CONFIG__
    const cfConfig = window.__CLOUDFORMATION_CONFIG__;
    if (cfConfig) {
      return {
        api: {
          baseUrl: cfConfig.ApiGatewayUrl
        },
        cognito: {
          userPoolId: cfConfig.UserPoolId,
          clientId: cfConfig.UserPoolClientId,
          domain: cfConfig.UserPoolDomain
        },
        aws: {
          region: 'us-east-1'
        },
        source: 'cloudformation'
      };
    }

    // Try to fetch from API endpoint with emergency fallback
    try {
      console.log('🔍 Fetching configuration from API...');
      const apiUrl = this.getApiBaseUrl();
      
      // Fetch from new configuration endpoint (no CloudFormation API calls)
      let response = await fetch(`${apiUrl}/api/config`);
      
      // If main endpoint fails, try health endpoint
      if (!response.ok && response.status === 503) {
        console.log('🔄 Main configuration endpoint failed, trying health endpoint...');
        response = await fetch(`${apiUrl}/api/config/health`);
      }
      
      if (response.ok) {
        // Check content type to ensure we're getting JSON, not HTML
        const contentType = response.headers.get('content-type');
        if (!contentType || !contentType.includes('application/json')) {
          console.warn('⚠️ Configuration endpoint returned non-JSON content:', contentType);
          console.warn('⚠️ This might be a routing issue or HTML error page');
          throw new Error('Invalid response type - expected JSON but got ' + (contentType || 'unknown'));
        }

        // Get response text first to check for HTML
        const responseText = await response.text();
        
        // Check if response is HTML (common in routing errors)
        if (responseText.includes('<!DOCTYPE') || responseText.includes('<html')) {
          console.error('🚨 Configuration endpoint returned HTML instead of JSON:');
          console.error('Response text:', responseText.substring(0, 200) + '...');
          throw new Error('Configuration endpoint returned HTML - possible routing misconfiguration');
        }

        try {
          const data = JSON.parse(responseText);
          const source = data.source === 'environment_variables' ? 'api' : 'health_api';
          console.log(`✅ Configuration fetched from ${source} (${data.source})`);
          
          return {
            api: {
              baseUrl: data.api?.gatewayUrl
            },
            cognito: {
              userPoolId: data.cognito?.userPoolId,
              clientId: data.cognito?.clientId,
              domain: data.cognito?.domain
            },
            aws: {
              region: data.cognito?.region || data.region || 'us-east-1'
            },
            source: source,
            environment: data.environment
          };
        } catch (parseError) {
          console.error('🚨 Failed to parse configuration response as JSON:');
          console.error('Parse error:', parseError.message);
          console.error('Response text:', responseText.substring(0, 500));
          throw new Error(`JSON parse error: ${parseError.message}`);
        }
      } else {
        console.warn('⚠️ Failed to fetch configuration from both main and health API:', response.status);
        
        // Log API error for debugging
        if (response.status === 500) {
          try {
            const errorData = await response.json();
            console.error('🔐 Configuration Service Error:', errorData.message || errorData.error);
            console.error('💡 Check Lambda environment variables and CloudFormation deployment');
          } catch (parseError) {
            console.error('🔐 Configuration Service Error: Unable to parse error response');
          }
        }
      }
    } catch (fetchError) {
      console.warn('⚠️ Error fetching configuration from API:', fetchError.message);
      
      // Provide more specific error messages
      if (fetchError.message.includes('HTML')) {
        console.error('🔧 SOLUTION: This looks like a routing issue. The API endpoint may be returning an HTML error page instead of JSON.');
        console.error('💡 Check your API Gateway configuration and ensure the /api/config endpoint is properly configured.');
      } else if (fetchError.message.includes('JSON')) {
        console.error('🔧 SOLUTION: JSON parsing failed. The API response may be malformed or empty.');
        console.error('💡 Check the API endpoint response format and ensure it returns valid JSON.');
      } else if (fetchError.message.includes('Failed to fetch')) {
        console.error('🔧 SOLUTION: Network request failed. Check your internet connection and API endpoint availability.');
      }
    }

    return {};
  }

  /**
   * Get API base URL for configuration fetching
   * Enhanced with intelligent URL resolution
   */
  async getApiBaseUrl() {
    try {
      // Use the new API URL resolver for intelligent detection
      const { default: apiUrlResolver } = await import('./apiUrlResolver');
      return await apiUrlResolver.getApiUrl();
    } catch (error) {
      console.warn('API URL resolver failed, using fallback:', error.message);
      return this.getApiBaseUrlSync();
    }
  }

  /**
   * Get API base URL synchronously (for backward compatibility)
   */
  getApiBaseUrlSync() {
    // Try multiple sources for API URL
    if (typeof window !== 'undefined' && window.__CONFIG__?.API?.BASE_URL) {
      return window.__CONFIG__.API.BASE_URL;
    }
    
    if (process.env.REACT_APP_API_URL) {
      return process.env.REACT_APP_API_URL;
    }

    // Check CloudFormation config
    if (typeof window !== 'undefined' && window.__CLOUDFORMATION_CONFIG__?.ApiGatewayUrl) {
      return window.__CLOUDFORMATION_CONFIG__.ApiGatewayUrl;
    }
    
    // Fallback to known CloudFormation output
    return 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev';
  }

  /**
   * Load window.__CONFIG__ if available
   */
  loadWindowConfig() {
    if (typeof window === 'undefined') return {};
    
    const windowConfig = window.__CONFIG__;
    if (!windowConfig) return {};
    
    return {
      api: {
        baseUrl: windowConfig.API?.BASE_URL || windowConfig.API_URL
      },
      cognito: {
        userPoolId: windowConfig.COGNITO?.USER_POOL_ID,
        clientId: windowConfig.COGNITO?.CLIENT_ID,
        domain: windowConfig.COGNITO?.DOMAIN
      },
      aws: {
        region: windowConfig.AWS?.REGION || 'us-east-1'
      },
      environment: windowConfig.ENVIRONMENT,
      source: 'window_config'
    };
  }

  /**
   * Load environment configuration
   */
  loadEnvironmentConfig() {
    return {
      api: {
        baseUrl: import.meta.env.VITE_API_URL
      },
      cognito: {
        userPoolId: import.meta.env.VITE_COGNITO_USER_POOL_ID,
        clientId: import.meta.env.VITE_COGNITO_CLIENT_ID,
        domain: import.meta.env.VITE_COGNITO_DOMAIN
      },
      aws: {
        region: import.meta.env.VITE_AWS_REGION || 'us-east-1'
      },
      source: 'environment'
    };
  }

  /**
   * Get default configuration
   */
  getDefaultConfig() {
    return {
      api: {
        baseUrl: 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev'
      },
      cognito: {
        userPoolId: null,
        clientId: null,
        domain: null
      },
      aws: {
        region: 'us-east-1'
      },
      features: {
        authentication: true,
        cognito: true
      },
      source: 'defaults'
    };
  }

  /**
   * Get safety fallback configuration for when everything fails
   */
  getSafetyFallbackConfig() {
    return {
      api: {
        baseUrl: 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev'
      },
      cognito: {
        userPoolId: null,
        clientId: null,
        domain: null
      },
      aws: {
        region: 'us-east-1'
      },
      features: {
        authentication: false, // Disable auth if config is broken
        cognito: false
      },
      source: 'safety_fallback',
      error: true
    };
  }

  /**
   * Merge configurations with proper priority
   */
  mergeConfigurations(...configs) {
    const result = {};
    
    // Merge in reverse priority order (lowest to highest)
    configs.reverse().forEach(config => {
      if (config && typeof config === 'object') {
        this.deepMerge(result, config);
      }
    });
    
    return result;
  }

  /**
   * Deep merge utility
   */
  deepMerge(target, source) {
    for (const key in source) {
      if (source.hasOwnProperty(key)) {
        if (source[key] && typeof source[key] === 'object' && !Array.isArray(source[key])) {
          target[key] = target[key] || {};
          this.deepMerge(target[key], source[key]);
        } else if (source[key] !== null && source[key] !== undefined) {
          target[key] = source[key];
        }
      }
    }
  }

  /**
   * Validate configuration
   */
  validateConfiguration(config) {
    const errors = [];
    const warnings = [];

    // Validate API configuration
    if (!config.api?.baseUrl) {
      errors.push('API base URL is required');
    } else if (config.api.baseUrl.includes('placeholder') || config.api.baseUrl.includes('example')) {
      warnings.push('API base URL appears to be a placeholder value');
    }

    // Validate Cognito configuration if authentication is enabled
    if (config.features?.authentication && config.features?.cognito) {
      if (!config.cognito?.userPoolId) {
        warnings.push('Cognito User Pool ID is missing - authentication may not work');
      } else if (this.isPlaceholderValue(config.cognito.userPoolId)) {
        warnings.push('Cognito User Pool ID appears to be a placeholder value');
      }

      if (!config.cognito?.clientId) {
        warnings.push('Cognito Client ID is missing - authentication may not work');
      } else if (this.isPlaceholderValue(config.cognito.clientId)) {
        warnings.push('Cognito Client ID appears to be a placeholder value');
      }
    }

    // Log validation results
    if (errors.length > 0) {
      console.error('❌ Configuration validation errors:', errors);
      throw new Error(`Configuration validation failed: ${errors.join(', ')}`);
    }

    if (warnings.length > 0) {
      console.warn('⚠️ Configuration validation warnings:', warnings);
    }
  }

  /**
   * Check if a value appears to be a placeholder
   */
  isPlaceholderValue(value) {
    if (!value || typeof value !== 'string') return true;
    
    const placeholderPatterns = [
      /^[a-z0-9]{32}$/i, // 32-character hex pattern like our example
      /dummy/i,
      /placeholder/i,
      /example/i,
      /test/i,
      /mock/i,
      /^us-east-1_DUMMY/,
      /undefined/,
      /null/
    ];
    
    return placeholderPatterns.some(pattern => pattern.test(value));
  }

  /**
   * Get current configuration
   */
  async getConfig() {
    if (!this.initialized) {
      await this.initialize();
    }
    return this.configCache;
  }

  /**
   * Get API configuration
   */
  async getApiConfig() {
    const config = await this.getConfig();
    return {
      baseUrl: config.api.baseUrl,
      timeout: 30000,
      retryAttempts: 3
    };
  }

  /**
   * Get Cognito configuration
   */
  async getCognitoConfig() {
    const config = await this.getConfig();
    return {
      userPoolId: config.cognito.userPoolId,
      clientId: config.cognito.clientId,
      domain: config.cognito.domain,
      region: config.aws.region,
      redirectSignIn: typeof window !== 'undefined' ? window.location.origin : '',
      redirectSignOut: typeof window !== 'undefined' ? window.location.origin : ''
    };
  }

  /**
   * Check if authentication is properly configured
   */
  async isAuthenticationConfigured() {
    const config = await this.getConfig();
    return !!(
      config.features?.authentication &&
      config.cognito?.userPoolId &&
      config.cognito?.clientId &&
      !this.isPlaceholderValue(config.cognito.userPoolId) &&
      !this.isPlaceholderValue(config.cognito.clientId)
    );
  }

  /**
   * Reset configuration cache (for testing)
   */
  reset() {
    this.configCache = null;
    this.initialized = false;
  }
}

// Create singleton instance
const configurationService = new ConfigurationService();

export default configurationService;