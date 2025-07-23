/**
 * Domain Service Tests
 * Tests for real domain configuration and fake URL replacement
 */

import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';
import domainService, { 
  getCurrentDomainConfig, 
  getApiUrlFromDomain, 
  isRealDomain, 
  replaceFakeUrls, 
  validateDomainUrls 
} from '../../../services/domainService';

// Mock fetch globally
global.fetch = vi.fn();

// Mock window.location
Object.defineProperty(window, 'location', {
  value: {
    hostname: 'localhost',
    protocol: 'http:',
    port: '3000',
    origin: 'http://localhost:3000'
  },
  writable: true
});

describe('DomainService - Real Domain Configuration', () => {
  beforeEach(() => {
    // Reset mocks before each test
    vi.clearAllMocks();
    
    // Reset domainService state
    domainService.domainConfig = null;
    domainService.initialized = false;
    
    // Reset window.location to localhost
    window.location.hostname = 'localhost';
    window.location.protocol = 'http:';
    window.location.port = '3000';
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Environment Detection', () => {
    test('should detect development environment', () => {
      window.location.hostname = 'localhost';
      
      const config = domainService.getEnvironmentBasedConfig();
      
      expect(config.environment).toBe('development');
      expect(config.hostname).toBe('localhost');
    });

    test('should detect staging environment', () => {
      window.location.hostname = 'staging.myapp.com';
      
      const config = domainService.getEnvironmentBasedConfig();
      
      expect(config.environment).toBe('staging');
      expect(config.hostname).toBe('staging.myapp.com');
    });

    test('should detect production environment', () => {
      window.location.hostname = 'myapp.com';
      
      const config = domainService.getEnvironmentBasedConfig();
      
      expect(config.environment).toBe('production');
      expect(config.hostname).toBe('myapp.com');
    });
  });

  describe('Real Domain Configuration', () => {
    test('should provide real AWS URLs for all environments', () => {
      const config = domainService.getEnvironmentBasedConfig();
      
      // Check all environments have real AWS URLs
      Object.values(config.domains).forEach(envConfig => {
        expect(envConfig.api).toContain('execute-api.amazonaws.com');
        expect(envConfig.websocket).toContain('execute-api.amazonaws.com');
        expect(envConfig.api).not.toContain('protrade.com');
        expect(envConfig.api).not.toContain('example.com');
      });
    });

    test('should use different stages for different environments', () => {
      const config = domainService.getEnvironmentBasedConfig();
      
      expect(config.domains.development.api).toContain('/dev');
      expect(config.domains.staging.api).toContain('/staging');
      expect(config.domains.production.api).toContain('/prod');
    });

    test('should configure real email addresses', () => {
      // Mock environment variables
      vi.stubGlobal('import.meta', {
        env: {
          VITE_DOMAIN_NAME: 'mycompany.com',
          VITE_SES_VERIFIED_DOMAIN: 'mycompany.com'
        }
      });

      const config = domainService.getEnvironmentBasedConfig();
      
      expect(config.email.support).toBe('support@mycompany.com');
      expect(config.email.noreply).toBe('noreply@mycompany.com');
      expect(config.email.alerts).toBe('alerts@mycompany.com');
    });
  });

  describe('Fake Domain Detection', () => {
    test('should identify fake domains correctly', () => {
      const fakeUrls = [
        'https://api.protrade.com/api',
        'https://protrade-analytics.com',
        'https://api-staging.protrade-analytics.com',
        'https://test-api.example.com/dev',
        'https://placeholder.com/api',
        'https://fake-api.com'
      ];

      fakeUrls.forEach(url => {
        expect(isRealDomain(url)).toBe(false);
      });
    });

    test('should identify real domains correctly', () => {
      const realUrls = [
        'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev',
        'wss://ckzvfd1ds3.execute-api.us-east-1.amazonaws.com/dev',
        'https://mycompany.com/api',
        'https://api.polygon.io',
        'https://data.alpaca.markets',
        'http://localhost:3000'
      ];

      realUrls.forEach(url => {
        expect(isRealDomain(url)).toBe(true);
      });
    });
  });

  describe('Fake URL Replacement', () => {
    test('should replace fake URLs with real AWS URLs', async () => {
      const fakeUrls = {
        api: 'https://api.protrade.com/api',
        websocket: 'wss://api.protrade.com/ws',
        frontend: 'https://protrade-analytics.com'
      };

      const replacedUrls = await replaceFakeUrls(fakeUrls);

      expect(replacedUrls.api).toContain('execute-api.amazonaws.com');
      expect(replacedUrls.websocket).toContain('execute-api.amazonaws.com');
      expect(replacedUrls.api).not.toContain('protrade.com');
      expect(replacedUrls.websocket).not.toContain('protrade.com');
    });

    test('should preserve real URLs during replacement', async () => {
      const mixedUrls = {
        api: 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev',
        fake: 'https://api.protrade.com/api',
        external: 'https://api.polygon.io'
      };

      const replacedUrls = await replaceFakeUrls(mixedUrls);

      expect(replacedUrls.api).toBe('https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev');
      expect(replacedUrls.external).toBe('https://api.polygon.io');
      expect(replacedUrls.fake).not.toContain('protrade.com');
    });
  });

  describe('URL Validation', () => {
    test('should validate URLs and identify issues', async () => {
      // Mock domain config with mixed real and fake URLs
      domainService.domainConfig = {
        domains: {
          development: {
            api: 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev',
            websocket: 'wss://ckzvfd1ds3.execute-api.us-east-1.amazonaws.com/dev',
            frontend: 'http://localhost:3000'
          },
          staging: {
            api: 'https://api.protrade.com/api', // Fake
            websocket: 'wss://api.protrade.com/ws', // Fake
            frontend: 'https://staging.protrade-analytics.com' // Fake
          }
        }
      };
      domainService.initialized = true;

      const issues = await validateDomainUrls();

      expect(issues).toHaveLength(3); // 3 fake URLs in staging
      expect(issues.every(issue => issue.environment === 'staging')).toBe(true);
      expect(issues.every(issue => issue.issue.includes('fake/placeholder'))).toBe(true);
    });

    test('should validate AWS API Gateway format', async () => {
      domainService.domainConfig = {
        domains: {
          production: {
            api: 'https://myapi.com/api', // Not AWS format
            websocket: 'wss://myws.com/ws' // Not AWS format
          }
        }
      };
      domainService.initialized = true;

      const issues = await validateDomainUrls();

      const apiIssues = issues.filter(i => i.service === 'api');
      const wsIssues = issues.filter(i => i.service === 'websocket');

      expect(apiIssues).toHaveLength(1);
      expect(wsIssues).toHaveLength(1);
      expect(apiIssues[0].issue).toContain('AWS API Gateway format');
      expect(wsIssues[0].issue).toContain('AWS WebSocket API Gateway format');
    });
  });

  describe('API Integration', () => {
    test('should fetch domain configuration from API', async () => {
      const mockConfig = {
        environment: 'production',
        domains: {
          production: {
            api: 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/prod',
            websocket: 'wss://ckzvfd1ds3.execute-api.us-east-1.amazonaws.com/prod'
          }
        }
      };

      // Mock successful API response
      fetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockConfig)
      });

      // Mock getApiUrl
      vi.doMock('../../../config/environment', () => ({
        getApiUrl: vi.fn(() => 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev')
      }));

      const config = await domainService.initialize();

      expect(config).toEqual(mockConfig);
      expect(fetch).toHaveBeenCalledWith(
        'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev/config/domain',
        expect.objectContaining({ method: 'GET' })
      );
    });

    test('should fallback to environment config when API fails', async () => {
      // Mock API failure
      fetch.mockRejectedValueOnce(new Error('API not available'));

      // Mock getApiUrl
      vi.doMock('../../../config/environment', () => ({
        getApiUrl: vi.fn(() => 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev')
      }));

      const config = await domainService.initialize();

      expect(config.environment).toBe('development');
      expect(config.domains.development.api).toContain('execute-api.amazonaws.com');
    });
  });

  describe('Real Domain Setup', () => {
    test('should setup real domains for deployment', async () => {
      const deploymentConfig = {
        customDomain: 'mycompany.com',
        apiGatewayUrl: 'https://abc123.execute-api.us-east-1.amazonaws.com/prod',
        webSocketUrl: 'wss://def456.execute-api.us-east-1.amazonaws.com/prod',
        sesVerifiedDomain: 'mycompany.com',
        cloudFrontDomain: 'd123abc.cloudfront.net'
      };

      // Mock successful API response
      fetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ success: true })
      });

      const realConfig = await domainService.setupRealDomains(deploymentConfig);

      expect(realConfig.domains.production.frontend).toBe('https://d123abc.cloudfront.net');
      expect(realConfig.domains.production.api).toBe(deploymentConfig.apiGatewayUrl);
      expect(realConfig.domains.production.websocket).toBe(deploymentConfig.webSocketUrl);
      expect(realConfig.email.support).toBe('support@mycompany.com');

      expect(fetch).toHaveBeenCalledWith(
        deploymentConfig.apiGatewayUrl + '/config/domain',
        expect.objectContaining({
          method: 'POST',
          body: expect.stringContaining('mycompany.com')
        })
      );
    });

    test('should handle setup failure', async () => {
      const deploymentConfig = {
        customDomain: 'mycompany.com',
        apiGatewayUrl: 'https://abc123.execute-api.us-east-1.amazonaws.com/prod',
        webSocketUrl: 'wss://def456.execute-api.us-east-1.amazonaws.com/prod',
        sesVerifiedDomain: 'mycompany.com'
      };

      // Mock API failure
      fetch.mockResolvedValueOnce({
        ok: false,
        status: 500
      });

      await expect(domainService.setupRealDomains(deploymentConfig)).rejects.toThrow(
        'Failed to save domain configuration: 500'
      );
    });
  });

  describe('Convenience Methods', () => {
    beforeEach(async () => {
      domainService.domainConfig = {
        environment: 'development',
        domains: {
          development: {
            api: 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev',
            websocket: 'wss://ckzvfd1ds3.execute-api.us-east-1.amazonaws.com/dev',
            frontend: 'http://localhost:3000'
          }
        }
      };
      domainService.initialized = true;
    });

    test('should get current API URL', async () => {
      const apiUrl = await getApiUrlFromDomain();
      
      expect(apiUrl).toBe('https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev');
    });

    test('should get current WebSocket URL', async () => {
      const wsUrl = await domainService.getWebSocketUrl();
      
      expect(wsUrl).toBe('wss://ckzvfd1ds3.execute-api.us-east-1.amazonaws.com/dev');
    });

    test('should get current frontend URL', async () => {
      const frontendUrl = await domainService.getFrontendUrl();
      
      expect(frontendUrl).toBe('http://localhost:3000');
    });

    test('should get current domain config', async () => {
      const config = await getCurrentDomainConfig();
      
      expect(config.api).toBe('https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev');
      expect(config.websocket).toBe('wss://ckzvfd1ds3.execute-api.us-east-1.amazonaws.com/dev');
      expect(config.frontend).toBe('http://localhost:3000');
    });
  });

  describe('No Fake URLs in Production', () => {
    test('should never return fake URLs', async () => {
      const config = await domainService.initialize();
      
      // Check all configured URLs
      Object.values(config.domains).forEach(envConfig => {
        Object.values(envConfig).forEach(url => {
          expect(url).not.toContain('protrade.com');
          expect(url).not.toContain('protrade-analytics.com');
          expect(url).not.toContain('example.com');
          expect(url).not.toContain('placeholder');
          expect(url).not.toContain('fake-api');
        });
      });

      // Check email configuration
      Object.values(config.email || {}).forEach(email => {
        expect(email).not.toContain('protrade.com');
        expect(email).not.toContain('example.com');
      });
    });

    test('should use real AWS services', () => {
      const config = domainService.getEnvironmentBasedConfig();
      
      // API should use AWS API Gateway
      Object.values(config.domains).forEach(envConfig => {
        if (!envConfig.api.includes('localhost')) {
          expect(envConfig.api).toContain('execute-api.amazonaws.com');
        }
        if (!envConfig.websocket.includes('localhost')) {
          expect(envConfig.websocket).toContain('execute-api.amazonaws.com');
        }
      });
    });
  });
});