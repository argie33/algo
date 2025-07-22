/**
 * API Configuration Smoke Tests
 * Catches API URL mismatches and configuration errors before production
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { createTestApiConfig, setupApiTestEnvironment, cleanupTestEnvironment } from '../setup/test-environment';
import { getApiConfig } from '../../services/api';

describe('🌐 API Configuration Smoke Tests', () => {

  afterEach(() => {
    cleanupTestEnvironment();
  });

  describe('API URL Resolution Priority', () => {
    it('should prioritize window.__CONFIG__.API_URL over environment variable', () => {
      const windowApiUrl = 'https://window-config-url.com/api';
      const envApiUrl = 'https://env-config-url.com/api';
      
      const testGetApiConfig = createTestApiConfig(windowApiUrl, envApiUrl);
      const config = testGetApiConfig();
      
      expect(config.apiUrl).toBe(windowApiUrl);
      expect(config.baseURL).toBe(windowApiUrl);
    });

    it('should fallback to environment variable when window config is missing', () => {
      const envApiUrl = 'https://env-fallback-url.com/api';
      
      const testGetApiConfig = createTestApiConfig(null, envApiUrl);
      const config = testGetApiConfig();
      
      expect(config.apiUrl).toBe(envApiUrl);
      expect(config.baseURL).toBe(envApiUrl);
    });

    it('should throw error when no API URL is configured', () => {
      const testGetApiConfig = createTestApiConfig(null, null);
      
      expect(() => {
        testGetApiConfig();
      }).toThrow('API URL not configured');
    });
  });

  describe('API URL Validation', () => {
    it('should detect localhost URLs as non-serverless', () => {
      global.window = { __CONFIG__: { API_URL: 'http://localhost:3000' } };
      
      const config = getApiConfig();
      expect(config.isServerless).toBe(false);
      expect(config.isConfigured).toBe(false);
    });

    it('should detect placeholder URLs as non-configured', () => {
      global.window = { __CONFIG__: { API_URL: 'PLACEHOLDER_URL' } };
      
      const config = getApiConfig();
      expect(config.isConfigured).toBe(false);
    });

    it('should detect valid AWS API Gateway URLs', () => {
      const awsApiUrl = 'https://abc123.execute-api.us-east-1.amazonaws.com/dev';
      global.window = { __CONFIG__: { API_URL: awsApiUrl } };
      
      const config = getApiConfig();
      expect(config.isServerless).toBe(true);
      expect(config.isConfigured).toBe(true);
      expect(config.apiUrl).toBe(awsApiUrl);
    });
  });

  describe('Environment Detection', () => {
    it('should correctly identify production environment', () => {
      vi.stubGlobal('import.meta', { 
        env: { 
          VITE_API_URL: 'https://api.example.com',
          MODE: 'production',
          DEV: false,
          PROD: true 
        } 
      });
      
      const config = getApiConfig();
      expect(config.environment).toBe('production');
      expect(config.isDevelopment).toBe(false);
      expect(config.isProduction).toBe(true);
    });

    it('should correctly identify development environment', () => {
      vi.stubGlobal('import.meta', { 
        env: { 
          VITE_API_URL: 'http://localhost:3000',
          MODE: 'development',
          DEV: true,
          PROD: false 
        } 
      });
      
      const config = getApiConfig();
      expect(config.environment).toBe('development');
      expect(config.isDevelopment).toBe(true);
      expect(config.isProduction).toBe(false);
    });
  });

  describe('URL Consistency Validation', () => {
    it('should warn about URL mismatches between window and env config', () => {
      const consoleSpy = vi.spyOn(console, 'log').mockImplementation(() => {});
      
      global.window = { 
        __CONFIG__: { API_URL: 'https://window-url.com/api' } 
      };
      
      vi.stubGlobal('import.meta', { 
        env: { VITE_API_URL: 'https://different-env-url.com/api' } 
      });
      
      const config = getApiConfig();
      
      expect(consoleSpy).toHaveBeenCalledWith(
        expect.stringContaining('🔧 [API CONFIG] URL Resolution:'),
        expect.objectContaining({
          windowConfig: 'https://window-url.com/api',
          envApiUrl: 'https://different-env-url.com/api',
          finalApiUrl: 'https://window-url.com/api'
        })
      );
      
      consoleSpy.mockRestore();
    });
  });

  describe('API Endpoint Validation', () => {
    it('should validate common API endpoints exist', () => {
      const baseUrl = 'https://api.example.com/dev';
      global.window = { __CONFIG__: { API_URL: baseUrl } };
      
      const config = getApiConfig();
      
      // Common endpoints that should be accessible
      const expectedEndpoints = [
        '/health',
        '/api/health', 
        '/stocks',
        '/api/settings/api-keys'
      ];
      
      expectedEndpoints.forEach(endpoint => {
        const fullUrl = `${config.baseURL}${endpoint}`;
        expect(fullUrl).toMatch(/^https:\/\/.+/);
        expect(fullUrl).not.toContain('undefined');
        expect(fullUrl).not.toContain('null');
      });
    });

    it('should reject invalid URL formats', () => {
      const invalidUrls = [
        '',
        null,
        undefined,
        'not-a-url',
        'http://',
        'https://',
        'ftp://invalid.com'
      ];
      
      invalidUrls.forEach(invalidUrl => {
        if (invalidUrl) {
          global.window = { __CONFIG__: { API_URL: invalidUrl } };
        } else {
          global.window = {};
          vi.stubGlobal('import.meta', { env: {} });
        }
        
        expect(() => {
          getApiConfig();
        }).toThrow();
      });
    });
  });
});