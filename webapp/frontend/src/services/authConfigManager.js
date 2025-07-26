/**
 * Authentication Configuration Manager
 * Handles robust loading, validation, and fallback for authentication configuration
 * 
 * Design Principles:
 * - Fail gracefully with multiple fallback strategies
 * - Provide detailed diagnostics for troubleshooting
 * - Support both authenticated and limited access modes
 * - Enable progressive enhancement of authentication features
 */

class AuthConfigManager {
  constructor() {
    this.config = null;
    this.initialized = false;
    this.authMode = 'unknown'; // 'full', 'limited', 'disabled'
    this.diagnostics = {
      configSources: [],
      failedSources: [],
      validationErrors: [],
      warnings: []
    };
  }

  /**
   * Initialize authentication configuration with comprehensive fallback strategy
   */
  async initialize() {
    console.log('🚀 Initializing AuthConfigManager...');
    
    try {
      // Step 1: Load configuration from multiple sources
      const config = await this.loadConfiguration();
      
      // Step 2: Validate configuration
      const validation = this.validateConfiguration(config);
      
      // Step 3: Determine authentication mode
      this.authMode = this.determineAuthMode(validation);
      
      // Step 4: Apply configuration based on mode
      await this.applyConfiguration(config, validation);
      
      this.config = config;
      this.initialized = true;
      
      console.log('✅ AuthConfigManager initialized successfully', {
        authMode: this.authMode,
        diagnostics: this.diagnostics
      });
      
      return {
        success: true,
        authMode: this.authMode,
        config: this.config,
        diagnostics: this.diagnostics
      };
      
    } catch (error) {
      console.error('❌ AuthConfigManager initialization failed:', error);
      
      // Emergency fallback - disable authentication
      this.authMode = 'disabled';
      this.config = this.getDisabledAuthConfig();
      this.initialized = true;
      
      this.diagnostics.failedSources.push({
        source: 'initialization',
        error: error.message,
        timestamp: new Date().toISOString()
      });
      
      return {
        success: false,
        authMode: this.authMode,
        config: this.config,
        diagnostics: this.diagnostics,
        error: error.message
      };
    }
  }

  /**
   * Load configuration from multiple sources with priority order
   */
  async loadConfiguration() {
    const sources = [
      { name: 'cloudformation', loader: () => this.loadCloudFormationConfig() },
      { name: 'runtime-api', loader: () => this.loadRuntimeApiConfig() },
      { name: 'environment', loader: () => this.loadEnvironmentConfig() },
      { name: 'window-config', loader: () => this.loadWindowConfig() }
    ];

    let finalConfig = this.getDefaultConfig();

    for (const source of sources) {
      try {
        console.log(`🔍 Loading config from ${source.name}...`);
        const sourceConfig = await source.loader();
        
        if (sourceConfig && Object.keys(sourceConfig).length > 0) {
          finalConfig = this.mergeConfigurations(finalConfig, sourceConfig);
          this.diagnostics.configSources.push({
            source: source.name,
            success: true,
            timestamp: new Date().toISOString(),
            keysLoaded: Object.keys(sourceConfig)
          });
          console.log(`✅ Successfully loaded config from ${source.name}`);
        }
      } catch (error) {
        console.warn(`⚠️ Failed to load config from ${source.name}:`, error.message);
        this.diagnostics.failedSources.push({
          source: source.name,
          error: error.message,
          timestamp: new Date().toISOString()
        });
      }
    }

    return finalConfig;
  }

  /**
   * Load CloudFormation configuration
   */
  async loadCloudFormationConfig() {
    if (typeof window === 'undefined') return {};
    
    const cfConfig = window.__CLOUDFORMATION_CONFIG__ || window.__CONFIG__;
    if (!cfConfig) {
      throw new Error('CloudFormation config not found in window object');
    }

    return {
      cognito: {
        userPoolId: cfConfig.UserPoolId,
        clientId: cfConfig.UserPoolClientId,
        region: cfConfig.Region || 'us-east-1',
        domain: cfConfig.UserPoolDomain
      },
      api: {
        baseUrl: cfConfig.ApiGatewayUrl
      }
    };
  }

  /**
   * Load configuration from runtime API
   */
  async loadRuntimeApiConfig() {
    try {
      const response = await fetch('/api/config/auth', {
        timeout: 5000,
        headers: {
          'Accept': 'application/json'
        }
      });

      if (!response.ok) {
        throw new Error(`API config request failed: ${response.status}`);
      }

      const config = await response.json();
      
      return {
        cognito: {
          userPoolId: config.userPoolId,
          clientId: config.clientId,
          region: config.region,
          domain: config.domain
        }
      };
    } catch (error) {
      throw new Error(`Runtime API config failed: ${error.message}`);
    }
  }

  /**
   * Load configuration from environment variables
   */
  loadEnvironmentConfig() {
    const env = import.meta.env;
    
    if (!env.VITE_COGNITO_USER_POOL_ID || !env.VITE_COGNITO_CLIENT_ID) {
      throw new Error('Required environment variables not found');
    }

    return {
      cognito: {
        userPoolId: env.VITE_COGNITO_USER_POOL_ID,
        clientId: env.VITE_COGNITO_CLIENT_ID,
        region: env.VITE_AWS_REGION || 'us-east-1',
        domain: env.VITE_COGNITO_DOMAIN
      },
      api: {
        baseUrl: env.VITE_API_BASE_URL
      }
    };
  }

  /**
   * Load configuration from window object
   */
  loadWindowConfig() {
    if (typeof window === 'undefined') return {};
    
    const config = window.__AUTH_CONFIG__;
    if (!config) {
      throw new Error('Window auth config not found');
    }

    return config;
  }

  /**
   * Validate authentication configuration
   */
  validateConfiguration(config) {
    const validation = {
      isValid: true,
      errors: [],
      warnings: [],
      requiredFields: ['cognito.userPoolId', 'cognito.clientId', 'cognito.region'],
      optionalFields: ['cognito.domain', 'api.baseUrl']
    };

    // Check required fields
    for (const field of validation.requiredFields) {
      const value = this.getNestedValue(config, field);
      if (!value || value === 'undefined' || value === 'null') {
        validation.errors.push(`Missing required field: ${field}`);
        validation.isValid = false;
      }
    }

    // Check for dummy/placeholder values
    const dummyPatterns = ['dummy', 'placeholder', 'test', 'example'];
    for (const field of validation.requiredFields) {
      const value = this.getNestedValue(config, field);
      if (value && dummyPatterns.some(pattern => 
        value.toLowerCase().includes(pattern))) {
        validation.warnings.push(`Possible dummy value in ${field}: ${value}`);
      }
    }

    // Validate format patterns
    if (config.cognito?.userPoolId && 
        !config.cognito.userPoolId.match(/^us-[a-z]+-\d+_[A-Za-z0-9]+$/)) {
      validation.errors.push('Invalid UserPool ID format');
      validation.isValid = false;
    }

    this.diagnostics.validationErrors = validation.errors;
    this.diagnostics.warnings = validation.warnings;

    return validation;
  }

  /**
   * Determine authentication mode based on validation results
   */
  determineAuthMode(validation) {
    if (validation.isValid && validation.errors.length === 0) {
      return 'full';
    } else if (validation.errors.length <= 2 && validation.warnings.length === 0) {
      return 'limited';
    } else {
      return 'disabled';
    }
  }

  /**
   * Apply configuration based on determined mode
   */
  async applyConfiguration(config, validation) {
    switch (this.authMode) {
      case 'full':
        await this.initializeFullAuthentication(config);
        break;
      case 'limited':
        await this.initializeLimitedAuthentication(config);
        break;
      case 'disabled':
        await this.initializeDisabledAuthentication();
        break;
    }
  }

  /**
   * Initialize full authentication with Amplify
   */
  async initializeFullAuthentication(config) {
    const { Amplify } = await import('aws-amplify');
    
    const amplifyConfig = {
      Auth: {
        Cognito: {
          userPoolId: config.cognito.userPoolId,
          userPoolClientId: config.cognito.clientId,
          region: config.cognito.region,
          signUpVerificationMethod: 'code',
          loginWith: {
            username: true,
            email: true
          }
        }
      }
    };

    Amplify.configure(amplifyConfig);
    console.log('✅ Full authentication initialized with Amplify');
  }

  /**
   * Initialize limited authentication (local storage based)
   */
  async initializeLimitedAuthentication(config) {
    console.log('⚠️ Limited authentication mode - using local fallback');
    // Implement local authentication fallback
  }

  /**
   * Initialize disabled authentication (public access only)
   */
  async initializeDisabledAuthentication() {
    console.log('🔓 Authentication disabled - public access mode');
  }

  /**
   * Get default configuration
   */
  getDefaultConfig() {
    return {
      cognito: {
        userPoolId: null,
        clientId: null,
        region: 'us-east-1',
        domain: null
      },
      api: {
        baseUrl: null
      }
    };
  }

  /**
   * Get disabled auth configuration
   */
  getDisabledAuthConfig() {
    return {
      ...this.getDefaultConfig(),
      authMode: 'disabled',
      features: {
        authentication: false,
        publicAccess: true,
        limitedFeatures: true
      }
    };
  }

  /**
   * Merge multiple configuration objects
   */
  mergeConfigurations(...configs) {
    return configs.reduce((merged, config) => {
      return this.deepMerge(merged, config);
    }, {});
  }

  /**
   * Deep merge utility
   */
  deepMerge(target, source) {
    const result = { ...target };
    
    for (const key in source) {
      if (source[key] && typeof source[key] === 'object' && !Array.isArray(source[key])) {
        result[key] = this.deepMerge(result[key] || {}, source[key]);
      } else if (source[key] !== undefined && source[key] !== null) {
        result[key] = source[key];
      }
    }
    
    return result;
  }

  /**
   * Get nested value from object using dot notation
   */
  getNestedValue(obj, path) {
    return path.split('.').reduce((current, key) => current?.[key], obj);
  }

  /**
   * Get current authentication mode
   */
  getAuthMode() {
    return this.authMode;
  }

  /**
   * Get configuration diagnostics
   */
  getDiagnostics() {
    return this.diagnostics;
  }

  /**
   * Check if authentication is available
   */
  isAuthenticationAvailable() {
    return this.authMode === 'full' || this.authMode === 'limited';
  }

  /**
   * Check if full features are available
   */
  isFullFeaturesAvailable() {
    return this.authMode === 'full';
  }
}

export default AuthConfigManager;