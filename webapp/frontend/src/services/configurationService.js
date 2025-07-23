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
      // Load from CloudFormation config if available
      const cloudFormationConfig = this.loadCloudFormationConfig();
      
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
      
      // Return safe fallback configuration
      this.configCache = this.getSafetyFallbackConfig();
      this.initialized = true;
      return this.configCache;
    }
  }

  /**
   * Load CloudFormation configuration if available
   */
  loadCloudFormationConfig() {
    if (typeof window === 'undefined') return {};
    
    const cfConfig = window.__CLOUDFORMATION_CONFIG__;
    if (!cfConfig) return {};
    
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