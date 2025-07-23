/**
 * Real Domain Configuration Service
 * Manages domain-specific configuration and replaces fake domains with real functionality
 */

import { getApiUrl } from '../config/environment';

class DomainService {
  constructor() {
    this.domainConfig = null;
    this.initialized = false;
  }

  async initialize() {
    if (this.initialized) return this.domainConfig;

    try {
      // Get domain configuration from API
      const apiUrl = getApiUrl();
      const response = await fetch(`${apiUrl}/config/domain`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        }
      });

      if (response.ok) {
        this.domainConfig = await response.json();
      } else {
        // Fallback to environment-based configuration
        this.domainConfig = this.getEnvironmentBasedConfig();
      }

      this.initialized = true;
      return this.domainConfig;

    } catch (error) {
      console.warn('Failed to fetch domain config from API, using environment fallback:', error);
      this.domainConfig = this.getEnvironmentBasedConfig();
      this.initialized = true;
      return this.domainConfig;
    }
  }

  /**
   * Get environment-based domain configuration
   */
  getEnvironmentBasedConfig() {
    const hostname = window.location.hostname;
    const protocol = window.location.protocol;
    const port = window.location.port;
    
    // Detect environment based on hostname
    let environment = 'production';
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
      environment = 'development';
    } else if (hostname.includes('staging') || hostname.includes('dev')) {
      environment = 'staging';
    }

    return {
      environment,
      hostname,
      protocol,
      port,
      
      // Real domain configuration
      domains: {
        development: {
          frontend: `${protocol}//${hostname}${port ? ':' + port : ''}`,
          api: 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev',
          websocket: 'wss://ckzvfd1ds3.execute-api.us-east-1.amazonaws.com/dev',
          support: this.getSupportDomain(environment)
        },
        staging: {
          frontend: `${protocol}//${hostname}`,
          api: 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/staging',
          websocket: 'wss://ckzvfd1ds3.execute-api.us-east-1.amazonaws.com/staging',
          support: this.getSupportDomain(environment)
        },
        production: {
          frontend: `${protocol}//${hostname}`,
          api: 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/prod',
          websocket: 'wss://ckzvfd1ds3.execute-api.us-east-1.amazonaws.com/prod',
          support: this.getSupportDomain(environment)
        }
      },

      // Email configuration
      email: {
        support: this.getSupportEmail(environment),
        noreply: this.getNoReplyEmail(environment),
        alerts: this.getAlertsEmail(environment)
      },

      // Feature flags based on domain/environment
      features: {
        realTrading: environment === 'production',
        debugMode: environment === 'development',
        analytics: environment !== 'development',
        errorTracking: environment !== 'development'
      }
    };
  }

  /**
   * Get support domain based on environment
   */
  getSupportDomain(environment) {
    const customDomain = import.meta.env.VITE_DOMAIN_NAME;
    
    if (customDomain) {
      return customDomain;
    }

    // Use AWS CloudFront distribution or S3 bucket domain as fallback
    if (environment === 'production') {
      return import.meta.env.VITE_CLOUDFRONT_DOMAIN || 'your-cloudfront-distribution.cloudfront.net';
    }
    
    return 'localhost:3000';
  }

  /**
   * Get support email based on environment
   */
  getSupportEmail(environment) {
    const customDomain = import.meta.env.VITE_DOMAIN_NAME;
    
    if (customDomain) {
      return `support@${customDomain}`;
    }

    // Use AWS SES verified domain
    const sesVerifiedDomain = import.meta.env.VITE_SES_VERIFIED_DOMAIN;
    if (sesVerifiedDomain) {
      return `support@${sesVerifiedDomain}`;
    }

    // Fallback to AWS SES sandbox email
    return import.meta.env.VITE_SUPPORT_EMAIL || 'support@aws-verified-domain.com';
  }

  /**
   * Get no-reply email
   */
  getNoReplyEmail(environment) {
    const customDomain = import.meta.env.VITE_DOMAIN_NAME;
    
    if (customDomain) {
      return `noreply@${customDomain}`;
    }

    const sesVerifiedDomain = import.meta.env.VITE_SES_VERIFIED_DOMAIN;
    if (sesVerifiedDomain) {
      return `noreply@${sesVerifiedDomain}`;
    }

    return import.meta.env.VITE_NOREPLY_EMAIL || 'noreply@aws-verified-domain.com';
  }

  /**
   * Get alerts email
   */
  getAlertsEmail(environment) {
    const customDomain = import.meta.env.VITE_DOMAIN_NAME;
    
    if (customDomain) {
      return `alerts@${customDomain}`;
    }

    const sesVerifiedDomain = import.meta.env.VITE_SES_VERIFIED_DOMAIN;
    if (sesVerifiedDomain) {
      return `alerts@${sesVerifiedDomain}`;
    }

    return import.meta.env.VITE_ALERTS_EMAIL || 'alerts@aws-verified-domain.com';
  }

  /**
   * Get current environment configuration
   */
  async getCurrentConfig() {
    const config = await this.initialize();
    return config.domains[config.environment];
  }

  /**
   * Get API URL for current environment
   */
  async getApiUrl() {
    const config = await this.getCurrentConfig();
    return config.api;
  }

  /**
   * Get WebSocket URL for current environment
   */
  async getWebSocketUrl() {
    const config = await this.getCurrentConfig();
    return config.websocket;
  }

  /**
   * Get frontend URL for current environment
   */
  async getFrontendUrl() {
    const config = await this.getCurrentConfig();
    return config.frontend;
  }

  /**
   * Validate if a URL is using a real domain (not fake/placeholder)
   */
  isRealDomain(url) {
    if (!url) return false;

    const fakeDomains = [
      'protrade.com',
      'api.protrade.com',
      'protrade-analytics.com',
      'api-staging.protrade-analytics.com',
      'example.com',
      'api.example.com',
      'test-api.example.com',
      'placeholder.com',
      'fake-api.com',
      'dummy.com'
    ];

    return !fakeDomains.some(fakeDomain => url.includes(fakeDomain));
  }

  /**
   * Replace fake URLs with real ones
   */
  async replaceFakeUrls(urls) {
    const config = await this.getCurrentConfig();
    const replaced = {};

    for (const [key, url] of Object.entries(urls)) {
      if (!this.isRealDomain(url)) {
        // Replace with appropriate real URL
        if (url.includes('api') || url.includes('gateway')) {
          replaced[key] = config.api;
        } else if (url.includes('ws') || url.includes('websocket')) {
          replaced[key] = config.websocket;
        } else {
          replaced[key] = config.frontend;
        }
        
        console.warn(`🔄 Replaced fake URL: ${url} -> ${replaced[key]}`);
      } else {
        replaced[key] = url;
      }
    }

    return replaced;
  }

  /**
   * Validate all configured URLs
   */
  async validateUrls() {
    const config = await this.initialize();
    const issues = [];

    for (const [env, envConfig] of Object.entries(config.domains)) {
      for (const [service, url] of Object.entries(envConfig)) {
        if (!this.isRealDomain(url)) {
          issues.push({
            environment: env,
            service,
            url,
            issue: 'Contains fake/placeholder domain'
          });
        }

        // Check for AWS API Gateway format
        if (service === 'api' && !url.includes('execute-api.') && !url.includes('localhost')) {
          issues.push({
            environment: env,
            service,
            url,
            issue: 'Should use AWS API Gateway format (execute-api.amazonaws.com)'
          });
        }

        // Check for AWS WebSocket format
        if (service === 'websocket' && !url.includes('execute-api.') && !url.includes('localhost')) {
          issues.push({
            environment: env,
            service,
            url,
            issue: 'Should use AWS WebSocket API Gateway format'
          });
        }
      }
    }

    return issues;
  }

  /**
   * Setup real domain configuration for deployment
   */
  async setupRealDomains(deploymentConfig) {
    const {
      customDomain,
      apiGatewayUrl,
      webSocketUrl,
      sesVerifiedDomain,
      cloudFrontDomain
    } = deploymentConfig;

    const realConfig = {
      domains: {
        production: {
          frontend: cloudFrontDomain ? `https://${cloudFrontDomain}` : `https://${customDomain}`,
          api: apiGatewayUrl,
          websocket: webSocketUrl,
          support: customDomain || cloudFrontDomain
        }
      },
      email: {
        support: `support@${sesVerifiedDomain || customDomain}`,
        noreply: `noreply@${sesVerifiedDomain || customDomain}`,
        alerts: `alerts@${sesVerifiedDomain || customDomain}`
      }
    };

    // Store configuration via API
    try {
      const response = await fetch(`${apiGatewayUrl}/config/domain`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(realConfig)
      });

      if (response.ok) {
        console.log('✅ Real domain configuration saved successfully');
        this.domainConfig = realConfig;
        return realConfig;
      } else {
        throw new Error(`Failed to save domain configuration: ${response.status}`);
      }
    } catch (error) {
      console.error('❌ Failed to save real domain configuration:', error);
      throw error;
    }
  }
}

// Export singleton instance
const domainService = new DomainService();
export default domainService;

// Named exports
export const getCurrentDomainConfig = () => domainService.getCurrentConfig();
export const getApiUrlFromDomain = () => domainService.getApiUrl();
export const getWebSocketUrlFromDomain = () => domainService.getWebSocketUrl();
export const isRealDomain = (url) => domainService.isRealDomain(url);
export const replaceFakeUrls = (urls) => domainService.replaceFakeUrls(urls);
export const validateDomainUrls = () => domainService.validateUrls();