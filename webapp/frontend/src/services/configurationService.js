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
      let cloudFormationConfig = {};
      
      // Try to load CloudFormation config with fallback
      try {
        cloudFormationConfig = await this.loadCloudFormationConfig();
      } catch (cfError) {
        console.warn('⚠️ CloudFormation config failed, using fallbacks:', cfError.message);
        cloudFormationConfig = {};
      }
      
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
      console.log('✅ Configuration initialized successfully');
      return this.configCache;
      
    } catch (error) {
      console.error('❌ Configuration initialization failed:', error);
      
      // Provide detailed error context
      const errorContext = {
        error: error.message,
        timestamp: new Date().toISOString(),
        attemptedSources: ['CloudFormation', 'Window Config', 'Environment Variables'],
        troubleshooting: {
          commonCauses: [
            'API Gateway not deployed or misconfigured',
            'CloudFormation stack outputs not properly set',
            'Environment variables missing or incorrect',
            'Network connectivity issues'
          ],
          nextSteps: [
            'Check API Gateway deployment status',
            'Verify CloudFormation stack outputs',
            'Ensure /api/config endpoint returns valid JSON',
            'Check browser network tab for actual API responses'
          ]
        }
      };
      
      console.error('🚨 Configuration Error Context:', errorContext);
      
      // Use emergency fallback configuration instead of failing completely
      console.warn('🚨 Using emergency fallback configuration to prevent app crash');
      this.configCache = this.getEmergencyFallbackConfig();
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
      const apiUrl = await this.getApiBaseUrl();
      
      // Fetch from new configuration endpoint (no CloudFormation API calls)
      let response = await fetch(`${apiUrl}/api/config`);
      
      // Don't try fallback endpoints - fail fast with clear error
      if (!response.ok) {
        const errorContext = {
          status: response.status,
          statusText: response.statusText,
          url: `${apiUrl}/api/config`,
          timestamp: new Date().toISOString()
        };
        console.error('🚨 Configuration API Error:', errorContext);
        throw new Error(`Configuration API returned ${response.status}: ${response.statusText}`);
      }
      
      if (response.ok) {
        // Check content type to ensure we're getting JSON, not HTML
        const contentType = response.headers.get('content-type');
        if (!contentType || !contentType.includes('application/json')) {
          const errorContext = {
            expectedContentType: 'application/json',
            actualContentType: contentType || 'unknown',
            url: `${apiUrl}/api/config`,
            possibleCauses: [
              'API Gateway routing misconfiguration',
              'Lambda function returning HTML error page',
              'CloudFront caching HTML instead of JSON',
              'API endpoint not properly configured'
            ],
            troubleshooting: [
              'Check API Gateway console for routing rules',
              'Verify Lambda function response format',
              'Clear CloudFront cache if applicable',
              'Test API endpoint directly with curl'
            ]
          };
          console.error('🚨 Content Type Error:', errorContext);
          throw new Error(`Configuration endpoint returned non-JSON content: ${contentType || 'unknown'}`);
        }

        // Get response text first to check for HTML
        const responseText = await response.text();
        
        // Check if response is HTML (common in routing errors)
        if (responseText.includes('<!DOCTYPE') || responseText.includes('<html')) {
          const errorContext = {
            responsePreview: responseText.substring(0, 500),
            detectedIssue: 'HTML response instead of JSON',
            likelyCauses: [
              'API Gateway returning default error page',
              'Lambda function exception causing HTML error response',
              'Incorrect routing configuration',
              'CloudFront serving cached HTML error page'
            ],
            immediateActions: [
              'Check Lambda function logs in CloudWatch',
              'Verify API Gateway stage deployment',
              'Test endpoint with curl: curl -H "Content-Type: application/json" ' + `${apiUrl}/api/config`,
              'Check CloudFront cache headers and invalidation'
            ]
          };
          console.error('🚨 HTML Response Error:', errorContext);
          throw new Error('Configuration endpoint returned HTML instead of JSON - API routing misconfiguration detected');
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
          const errorContext = {
            parseError: parseError.message,
            responsePreview: responseText.substring(0, 500),
            responseLength: responseText.length,
            contentType: response.headers.get('content-type'),
            troubleshooting: [
              'Response is not valid JSON format',
              'API may be returning partial or corrupted response',
              'Check Lambda function return format',
              'Verify API Gateway response mapping'
            ]
          };
          console.error('🚨 JSON Parse Error:', errorContext);
          throw new Error(`Configuration API returned invalid JSON: ${parseError.message}`);
        }
      }
    } catch (fetchError) {
      // Get API URL safely for error context
      let errorUrl;
      try {
        const apiUrlForError = await this.getApiBaseUrl();
        errorUrl = `${apiUrlForError}/api/config`;
      } catch (urlError) {
        errorUrl = 'URL_RESOLUTION_FAILED';
      }
      
      const errorContext = {
        error: fetchError.message,
        url: errorUrl,
        timestamp: new Date().toISOString(),
        troubleshooting: {
          networkErrors: fetchError.message.includes('fetch') ? [
            'Check internet connectivity',
            'Verify API Gateway URL is correct',
            'Check CORS configuration',
            'Ensure API Gateway is deployed and accessible'
          ] : [],
          htmlErrors: fetchError.message.includes('HTML') ? [
            'API Gateway returning HTML error page instead of JSON',
            'Check Lambda function logs for exceptions',
            'Verify API Gateway routing configuration',
            'Check CloudFront cache settings'
          ] : [],
          jsonErrors: fetchError.message.includes('JSON') ? [
            'API response is not valid JSON',
            'Check Lambda function response format',
            'Verify API Gateway response mapping templates',
            'Ensure content-type headers are correct'
          ] : []
        }
      };
      console.error('🚨 Configuration Fetch Error:', errorContext);
      throw fetchError;
    }
  }

  /**
   * Get API base URL for configuration fetching
   * No fallbacks - fail fast if URL resolution fails
   */
  async getApiBaseUrl() {
    try {
      // Use the new API URL resolver for intelligent detection
      const { default: apiUrlResolver } = await import('./apiUrlResolver');
      return await apiUrlResolver.getApiUrl();
    } catch (error) {
      const errorContext = {
        error: error.message,
        module: 'apiUrlResolver',
        fallbackAttempted: false,
        troubleshooting: [
          'Check if apiUrlResolver module exists and is properly exported',
          'Verify API URL configuration in environment variables',
          'Ensure CloudFormation outputs are properly set',
          'Check for import/export syntax errors in apiUrlResolver'
        ]
      };
      console.error('🚨 API URL Resolution Error:', errorContext);
      throw new Error(`API URL resolution failed: ${error.message}`);
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
   * Get emergency fallback configuration to prevent app crash
   */
  getEmergencyFallbackConfig() {
    return {
      api: {
        baseUrl: 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev'
      },
      cognito: {
        userPoolId: 'us-east-1_EMERGENCY',
        clientId: 'emergency_client_id',
        domain: 'emergency-domain'
      },
      aws: {
        region: 'us-east-1'
      },
      features: {
        authentication: false, // Disable auth in emergency mode
        cognito: false
      },
      emergency: true,
      source: 'emergency_fallback',
      message: 'Running in emergency mode - some features may be disabled'
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
    
    // Don't try to configure auth in emergency mode
    if (config.emergency) {
      console.warn('⚠️ Emergency mode active - authentication disabled');
      return false;
    }
    
    // Check authentication feature flag
    if (!config.features?.authentication) {
      console.warn('⚠️ Authentication feature disabled in configuration');
      return false;
    }
    
    // Validate Cognito configuration
    const hasUserPoolId = config.cognito?.userPoolId;
    const hasClientId = config.cognito?.clientId;
    const userPoolIdValid = hasUserPoolId && !this.isPlaceholderValue(config.cognito.userPoolId);
    const clientIdValid = hasClientId && !this.isPlaceholderValue(config.cognito.clientId);
    
    if (!hasUserPoolId) {
      console.error('❌ Missing Cognito User Pool ID in configuration');
    } else if (!userPoolIdValid) {
      console.error('❌ Cognito User Pool ID is placeholder/invalid:', config.cognito.userPoolId);
    }
    
    if (!hasClientId) {
      console.error('❌ Missing Cognito Client ID in configuration');
    } else if (!clientIdValid) {
      console.error('❌ Cognito Client ID is placeholder/invalid:', config.cognito.clientId);
    }
    
    const isConfigured = userPoolIdValid && clientIdValid;
    
    if (!isConfigured) {
      console.error('❌ Authentication configuration validation failed:', {
        userPoolId: config.cognito?.userPoolId || 'missing',
        clientId: config.cognito?.clientId || 'missing',
        userPoolIdValid,
        clientIdValid
      });
    }
    
    return isConfigured;
  }

  /**
   * Check if running in emergency mode
   */
  async isEmergencyMode() {
    const config = await this.getConfig();
    return config.emergency === true;
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