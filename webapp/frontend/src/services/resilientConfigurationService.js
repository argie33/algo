/**
 * Resilient Configuration Service - Bulletproof Multi-Layer Design
 * 
 * FEATURES:
 * ✅ Defense-in-depth configuration loading
 * ✅ Guaranteed fallbacks that never fail
 * ✅ HTML/JSON response validation
 * ✅ Circuit breaker per configuration layer
 * ✅ Progressive enhancement through layers
 * ✅ Offline mode capability
 */

// Configuration Layers (in priority order)
class CloudFormationConfigLayer {
  constructor() {
    this.name = 'cloudformation';
    this.timeout = 8000;
  }

  async fetchConfig() {
    if (typeof window === 'undefined') return null;
    
    const cfConfig = window.__CLOUDFORMATION_CONFIG__;
    if (cfConfig?.ApiGatewayUrl) {
      return {
        api: { baseUrl: cfConfig.ApiGatewayUrl },
        cognito: {
          userPoolId: cfConfig.UserPoolId,
          clientId: cfConfig.UserPoolClientId,
          domain: cfConfig.UserPoolDomain
        },
        aws: { region: 'us-east-1' },
        source: 'cloudformation'
      };
    }
    
    throw new Error('CloudFormation config not available');
  }
}

class ApiConfigLayer {
  constructor() {
    this.name = 'api';
    this.timeout = 10000;
  }

  async fetchConfig() {
    const apiUrl = this.getApiBaseUrl();
    if (!apiUrl) {
      throw new Error('API base URL not available');
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeout);

    try {
      const response = await fetch(`${apiUrl}/api/config`, {
        signal: controller.signal,
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        }
      });

      clearTimeout(timeoutId);

      // Validate response before processing
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      // Critical: Validate content type
      const contentType = response.headers.get('content-type');
      if (!contentType?.includes('application/json')) {
        throw new Error(`Invalid content type: ${contentType}, expected JSON`);
      }

      const responseText = await response.text();
      
      // Critical: Check for HTML response (common error)
      if (this.isHtmlResponse(responseText)) {
        throw new Error('API returned HTML instead of JSON - routing misconfiguration');
      }

      const data = JSON.parse(responseText);
      
      return {
        api: { baseUrl: data.api?.gatewayUrl },
        cognito: {
          userPoolId: data.cognito?.userPoolId,
          clientId: data.cognito?.clientId,
          domain: data.cognito?.domain
        },
        aws: { region: data.cognito?.region || 'us-east-1' },
        source: 'api'
      };

    } finally {
      clearTimeout(timeoutId);
    }
  }

  getApiBaseUrl() {
    return import.meta.env.VITE_API_BASE_URL || 
           window.__CONFIG__?.API?.BASE_URL ||
           'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev';
  }

  isHtmlResponse(text) {
    const htmlIndicators = ['<!DOCTYPE', '<html', '<HTML', '<!doctype'];
    return htmlIndicators.some(indicator => 
      text.trim().toLowerCase().startsWith(indicator.toLowerCase())
    );
  }
}

class EnvironmentConfigLayer {
  constructor() {
    this.name = 'environment';
  }

  async fetchConfig() {
    const envConfig = {
      api: { baseUrl: import.meta.env.VITE_API_BASE_URL },
      cognito: {
        userPoolId: import.meta.env.VITE_COGNITO_USER_POOL_ID,
        clientId: import.meta.env.VITE_COGNITO_CLIENT_ID,
        domain: import.meta.env.VITE_COGNITO_DOMAIN
      },
      aws: { region: import.meta.env.VITE_AWS_REGION || 'us-east-1' },
      source: 'environment'
    };

    // Validate at least API URL is present
    if (!envConfig.api.baseUrl) {
      throw new Error('Environment configuration incomplete');
    }

    return envConfig;
  }
}

class StaticFallbackLayer {
  constructor() {
    this.name = 'static_fallback';
  }

  async fetchConfig() {
    return {
      api: { baseUrl: 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev' },
      cognito: {
        userPoolId: null,
        clientId: null,
        domain: null
      },
      aws: { region: 'us-east-1' },
      features: { authentication: false },
      source: 'static_fallback'
    };
  }
}

class EmergencyOfflineLayer {
  constructor() {
    this.name = 'emergency_offline';
  }

  async fetchConfig() {
    return {
      api: { baseUrl: null },
      cognito: { userPoolId: null, clientId: null, domain: null },
      aws: { region: 'us-east-1' },
      features: { 
        authentication: false,
        offlineMode: true,
        limitedFunctionality: true
      },
      emergency: true,
      source: 'emergency_offline',
      message: 'Running in offline emergency mode - limited functionality'
    };
  }
}

// Configuration Validation Chain
class ConfigValidationChain {
  validate(config) {
    if (!config || typeof config !== 'object') {
      throw new Error('Invalid configuration object');
    }

    // Validate structure
    const validatedConfig = {
      api: this.validateApiConfig(config.api),
      cognito: this.validateCognitoConfig(config.cognito),
      aws: this.validateAwsConfig(config.aws),
      features: config.features || {},
      source: config.source,
      emergency: config.emergency || false
    };

    // Add metadata
    validatedConfig.validated = true;
    validatedConfig.validatedAt = new Date().toISOString();
    
    return validatedConfig;
  }

  validateApiConfig(api) {
    if (!api) return { baseUrl: null };
    
    return {
      baseUrl: this.validateUrl(api.baseUrl),
      timeout: api.timeout || 30000,
      retryAttempts: api.retryAttempts || 3
    };
  }

  validateCognitoConfig(cognito) {
    if (!cognito) return { userPoolId: null, clientId: null, domain: null };
    
    return {
      userPoolId: this.validateString(cognito.userPoolId),
      clientId: this.validateString(cognito.clientId), 
      domain: this.validateString(cognito.domain)
    };
  }

  validateAwsConfig(aws) {
    return {
      region: aws?.region || 'us-east-1'
    };
  }

  validateUrl(url) {
    if (!url || typeof url !== 'string') return null;
    
    // Check for placeholder URLs
    const placeholders = ['example.com', 'placeholder', 'your-domain'];
    if (placeholders.some(p => url.includes(p))) {
      return null;
    }
    
    return url;
  }

  validateString(str) {
    if (!str || typeof str !== 'string' || str.trim() === '') return null;
    
    // Check for placeholder values
    const placeholders = ['PLACEHOLDER', 'DUMMY', 'EXAMPLE', 'TODO'];
    if (placeholders.some(p => str.toUpperCase().includes(p))) {
      return null;
    }
    
    return str.trim();
  }
}

// Circuit Breaker for Configuration Layers
class ConfigCircuitBreaker {
  constructor() {
    this.states = new Map();
    this.failureThreshold = 3;
    this.timeout = 60000; // 1 minute
    this.successThreshold = 2;
  }

  canAttempt(layerName) {
    const state = this.getState(layerName);
    
    if (state.status === 'CLOSED') return true;
    if (state.status === 'HALF_OPEN') return state.attempts < this.successThreshold;
    if (state.status === 'OPEN') {
      if (Date.now() - state.lastFailure > this.timeout) {
        state.status = 'HALF_OPEN';
        state.attempts = 0;
        return true;
      }
      return false;
    }
    
    return true;
  }

  recordSuccess(layerName) {
    const state = this.getState(layerName);
    
    if (state.status === 'HALF_OPEN') {
      state.attempts++;
      if (state.attempts >= this.successThreshold) {
        state.status = 'CLOSED';
        state.failures = 0;
      }
    } else {
      state.status = 'CLOSED'; 
      state.failures = 0;
    }
  }

  recordFailure(layerName, error) {
    const state = this.getState(layerName);
    state.failures++;
    state.lastFailure = Date.now();
    state.lastError = error.message;

    if (state.failures >= this.failureThreshold) {
      state.status = 'OPEN';
    }

    console.warn(`Config layer ${layerName} circuit breaker: ${state.status} (failures: ${state.failures})`);
  }

  getState(layerName) {
    if (!this.states.has(layerName)) {
      this.states.set(layerName, {
        status: 'CLOSED',
        failures: 0,
        attempts: 0,
        lastFailure: 0,
        lastError: null
      });
    }
    return this.states.get(layerName);
  }
}

// Main Resilient Configuration Service
class ResilientConfigurationService {
  constructor() {
    this.configLayers = [
      new CloudFormationConfigLayer(),
      new ApiConfigLayer(),
      new EnvironmentConfigLayer(), 
      new StaticFallbackLayer(),
      new EmergencyOfflineLayer()
    ];
    
    this.validationChain = new ConfigValidationChain();
    this.circuitBreaker = new ConfigCircuitBreaker();
    this.configCache = null;
    this.initialized = false;
  }

  async initialize() {
    if (this.initialized && this.configCache) {
      return this.configCache;
    }

    console.log('🔧 Initializing resilient configuration service...');
    
    // Try each layer with circuit breaker protection
    for (const layer of this.configLayers) {
      try {
        if (this.circuitBreaker.canAttempt(layer.name)) {
          console.log(`🔍 Attempting config layer: ${layer.name}`);
          
          const config = await layer.fetchConfig();
          const validConfig = this.validationChain.validate(config);
          
          this.circuitBreaker.recordSuccess(layer.name);
          this.configCache = this.enrichConfig(validConfig);
          this.initialized = true;
          
          console.log(`✅ Configuration loaded from ${layer.name}`);
          return this.configCache;
        } else {
          console.log(`⏭️ Skipping ${layer.name} - circuit breaker OPEN`);
        }
      } catch (error) {
        this.circuitBreaker.recordFailure(layer.name, error);
        console.warn(`❌ Config layer ${layer.name} failed: ${error.message}`);
      }
    }

    // This should never happen due to EmergencyOfflineLayer
    throw new Error('All configuration layers failed - this should not be possible');
  }

  enrichConfig(config) {
    // Add computed properties and helpers
    return {
      ...config,
      
      // Computed properties
      isOnline: !config.emergency,
      hasAuthentication: !!(config.cognito?.userPoolId && config.cognito?.clientId),
      hasApiAccess: !!config.api?.baseUrl,
      
      // Helper methods
      getApiUrl: (endpoint = '') => {
        if (!config.api?.baseUrl) return null;
        const baseUrl = config.api.baseUrl.replace(/\/$/, '');
        const cleanEndpoint = endpoint.replace(/^\//, '');
        return `${baseUrl}/${cleanEndpoint}`;
      },
      
      getCognitoConfig: () => ({
        ...config.cognito,
        region: config.aws.region,
        redirectSignIn: typeof window !== 'undefined' ? window.location.origin : '',
        redirectSignOut: typeof window !== 'undefined' ? window.location.origin : ''
      }),
      
      // Metadata
      loadedAt: new Date().toISOString(),
      version: '2.0.0'
    };
  }

  async getConfig() {
    if (!this.initialized) {
      await this.initialize();
    }
    return this.configCache;
  }

  // Get configuration status for debugging
  getStatus() {
    const states = {};
    for (const layer of this.configLayers) {
      states[layer.name] = this.circuitBreaker.getState(layer.name);
    }
    
    return {
      initialized: this.initialized,
      hasConfig: !!this.configCache,
      currentSource: this.configCache?.source,
      layerStates: states,
      timestamp: new Date().toISOString()
    };
  }

  // Force reset for testing
  reset() {
    this.configCache = null;
    this.initialized = false;
    this.circuitBreaker = new ConfigCircuitBreaker();
  }
}

// Create singleton instance
const resilientConfigurationService = new ResilientConfigurationService();

export default resilientConfigurationService;