/**
 * CloudFormation Configuration Service
 * Fetches real AWS resource configuration from CloudFormation stack outputs
 * Replaces all hardcoded placeholder values with actual deployed resources
 */

import { getApiUrl } from '../config/environment';

class CloudFormationConfigService {
  constructor() {
    this.config = null;
    this.initialized = false;
    this.stackName = null;
    this.apiUrl = null;
  }

  /**
   * Initialize the service and detect stack name
   */
  async initialize() {
    if (this.initialized) return this.config;

    try {
      // Get API URL from environment configuration
      this.apiUrl = getApiUrl();
      
      // Detect stack name from environment or API URL
      this.stackName = this.detectStackName();
      
      console.log(`🏗️ Initializing CloudFormation config service for stack: ${this.stackName}`);
      
      // Fetch real configuration from CloudFormation via API
      this.config = await this.fetchCloudFormationConfig();
      
      this.initialized = true;
      return this.config;
      
    } catch (error) {
      console.error('❌ Failed to initialize CloudFormation config service:', error);
      // Fallback to environment-based configuration
      this.config = this.getEnvironmentFallbackConfig();
      this.initialized = true;
      return this.config;
    }
  }

  /**
   * Detect CloudFormation stack name from environment or URL patterns
   */
  detectStackName() {
    // Try environment variable first
    if (import.meta.env.VITE_CF_STACK_NAME) {
      return import.meta.env.VITE_CF_STACK_NAME;
    }
    
    // Try window config
    if (window.__CONFIG__?.CF_STACK_NAME) {
      return window.__CONFIG__.CF_STACK_NAME;
    }

    // Detect from hostname
    const hostname = window.location.hostname;
    
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
      return 'stocks-webapp-dev';
    } else if (hostname.includes('staging') || hostname.includes('dev')) {
      return 'stocks-webapp-staging'; 
    } else {
      return 'stocks-webapp-prod';
    }
  }

  /**
   * Fetch real CloudFormation configuration from API
   */
  async fetchCloudFormationConfig() {
    try {
      console.log(`🔍 Fetching CloudFormation outputs for stack: ${this.stackName}`);
      
      const response = await fetch(`${this.apiUrl}/api/config/cloudformation?stackName=${this.stackName}`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        }
      });

      if (!response.ok) {
        throw new Error(`CloudFormation API returned ${response.status}: ${response.statusText}`);
      }

      const cloudFormationConfig = await response.json();
      
      console.log('✅ CloudFormation configuration fetched successfully');
      
      // Transform CloudFormation outputs to application configuration
      return this.transformCloudFormationOutputs(cloudFormationConfig);
      
    } catch (error) {
      console.error('❌ Failed to fetch CloudFormation config from API:', error);
      throw error;
    }
  }

  /**
   * Transform CloudFormation stack outputs to application configuration
   */
  transformCloudFormationOutputs(cfOutputs) {
    const outputs = cfOutputs.outputs || {};
    
    return {
      // API Configuration - from real CloudFormation outputs
      api: {
        baseUrl: outputs.ApiGatewayUrl || this.apiUrl,
        gatewayId: outputs.ApiGatewayId,
        stageName: outputs.ApiGatewayStageName || 'dev'
      },
      
      // Cognito Configuration - from real CloudFormation outputs  
      cognito: {
        userPoolId: outputs.UserPoolId,
        clientId: outputs.UserPoolClientId,
        domain: outputs.UserPoolDomain,
        region: cfOutputs.region || 'us-east-1'
      },
      
      // Frontend Configuration - from real CloudFormation outputs
      frontend: {
        bucketName: outputs.FrontendBucketName,
        cloudFrontId: outputs.CloudFrontDistributionId,
        websiteUrl: outputs.WebsiteURL
      },
      
      // Lambda Configuration - from real CloudFormation outputs
      lambda: {
        functionName: outputs.LambdaFunctionName,
        functionArn: outputs.LambdaFunctionArn
      },
      
      // Stack Information
      stack: {
        name: this.stackName,
        environment: outputs.EnvironmentName || this.detectEnvironment(),
        region: cfOutputs.region || 'us-east-1',
        accountId: outputs.AccountId
      },
      
      // Metadata
      metadata: {
        fetchedAt: new Date().toISOString(),
        source: 'cloudformation',
        apiUrl: this.apiUrl,
        stackName: this.stackName
      }
    };
  }

  /**
   * Get environment fallback configuration when CloudFormation is not available
   */
  getEnvironmentFallbackConfig() {
    console.warn('⚠️ Using environment fallback configuration - CloudFormation outputs not available');
    
    const environment = this.detectEnvironment();
    
    return {
      api: {
        baseUrl: this.apiUrl,
        gatewayId: 'unknown',
        stageName: environment
      },
      cognito: {
        userPoolId: import.meta.env.VITE_COGNITO_USER_POOL_ID || null,
        clientId: import.meta.env.VITE_COGNITO_CLIENT_ID || null,
        domain: import.meta.env.VITE_COGNITO_DOMAIN || null,
        region: import.meta.env.VITE_AWS_REGION || 'us-east-1'
      },
      frontend: {
        bucketName: 'unknown',
        cloudFrontId: 'unknown', 
        websiteUrl: window.location.origin
      },
      lambda: {
        functionName: 'unknown',
        functionArn: 'unknown'
      },
      stack: {
        name: this.stackName,
        environment,
        region: import.meta.env.VITE_AWS_REGION || 'us-east-1',
        accountId: 'unknown'
      },
      metadata: {
        fetchedAt: new Date().toISOString(),
        source: 'environment-fallback',
        apiUrl: this.apiUrl,
        stackName: this.stackName
      }
    };
  }

  /**
   * Detect current environment
   */
  detectEnvironment() {
    const hostname = window.location.hostname;
    
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
      return 'dev';
    } else if (hostname.includes('staging') || hostname.includes('dev')) {
      return 'staging';
    } else {
      return 'prod';
    }
  }

  /**
   * Get real Cognito configuration
   */
  async getCognitoConfig() {
    const config = await this.initialize();
    return config.cognito;
  }

  /**
   * Get real API configuration  
   */
  async getApiConfig() {
    const config = await this.initialize();
    return config.api;
  }

  /**
   * Get real frontend configuration
   */
  async getFrontendConfig() {
    const config = await this.initialize();
    return config.frontend;
  }

  /**
   * Get full real configuration
   */
  async getRealConfig() {
    return await this.initialize();
  }

  /**
   * Validate that all required real values are present
   */
  async validateRealConfig() {
    const config = await this.initialize();
    const issues = [];
    
    // Validate Cognito configuration
    if (!config.cognito.userPoolId) {
      issues.push('Cognito User Pool ID is missing');
    }
    
    if (!config.cognito.clientId) {
      issues.push('Cognito Client ID is missing');
    }
    
    // Validate API configuration
    if (!config.api.baseUrl || config.api.baseUrl.includes('protrade.com')) {
      issues.push('API base URL is missing or contains fake domain');
    }
    
    // Validate that we're using real AWS resources
    if (!config.api.baseUrl.includes('execute-api.amazonaws.com') && 
        !config.api.baseUrl.includes('localhost')) {
      issues.push('API URL does not appear to be a real AWS API Gateway');
    }
    
    return {
      isValid: issues.length === 0,
      issues,
      config,
      source: config.metadata.source
    };
  }

  /**
   * Update runtime configuration with real CloudFormation values
   */
  async updateRuntimeConfig() {
    const config = await this.initialize();
    
    // Update window.__CONFIG__ with real values
    if (window.__CONFIG__) {
      window.__CONFIG__.API.BASE_URL = config.api.baseUrl;
      window.__CONFIG__.COGNITO.USER_POOL_ID = config.cognito.userPoolId;
      window.__CONFIG__.COGNITO.CLIENT_ID = config.cognito.clientId;
      window.__CONFIG__.COGNITO.DOMAIN = config.cognito.domain;
      window.__CONFIG__.COGNITO.REGION = config.cognito.region;
      
      // Add CloudFormation metadata
      window.__CONFIG__.CLOUDFORMATION = {
        STACK_NAME: config.stack.name,
        ENVIRONMENT: config.stack.environment,
        FETCHED_AT: config.metadata.fetchedAt,
        SOURCE: config.metadata.source
      };
      
      console.log('✅ Runtime configuration updated with real CloudFormation values');
    }
    
    return config;
  }

  /**
   * Force refresh configuration from CloudFormation
   */
  async refreshConfig() {
    this.config = null;
    this.initialized = false;
    return await this.initialize();
  }

  /**
   * Get configuration summary for debugging
   */
  async getConfigSummary() {
    const config = await this.initialize();
    
    return {
      source: config.metadata.source,
      stackName: config.stack.name,
      environment: config.stack.environment,
      apiUrl: config.api.baseUrl,
      cognitoConfigured: !!(config.cognito.userPoolId && config.cognito.clientId),
      fetchedAt: config.metadata.fetchedAt,
      isRealConfig: config.metadata.source === 'cloudformation',
      hasPlaceholders: config.api.baseUrl.includes('protrade.com') || 
                     config.api.baseUrl.includes('example.com')
    };
  }
}

// Export singleton instance
const cloudFormationConfigService = new CloudFormationConfigService();
export default cloudFormationConfigService;

// Named exports for convenience
export const getCognitoConfig = () => cloudFormationConfigService.getCognitoConfig();
export const getApiConfig = () => cloudFormationConfigService.getApiConfig(); 
export const getFrontendConfig = () => cloudFormationConfigService.getFrontendConfig();
export const getRealConfig = () => cloudFormationConfigService.getRealConfig();
export const validateRealConfig = () => cloudFormationConfigService.validateRealConfig();
export const updateRuntimeConfig = () => cloudFormationConfigService.updateRuntimeConfig();
export const getConfigSummary = () => cloudFormationConfigService.getConfigSummary();