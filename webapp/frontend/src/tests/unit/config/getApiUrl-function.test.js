/**
 * getApiUrl Function Unit Tests
 * Tests the exact function used by dataCache.js and other services
 */

import { describe, test, expect, beforeEach, vi } from 'vitest'

// Mock environment variables before importing the function
const mockEnv = {
  VITE_API_BASE_URL: undefined,
  NODE_ENV: 'test'
}

vi.stubGlobal('import.meta', {
  env: mockEnv
})

// Mock window config
const mockWindowConfig = {}
vi.stubGlobal('window', {
  __CONFIG__: mockWindowConfig,
  __RUNTIME_CONFIG__: {},
  location: { origin: 'http://localhost:3000' }
})

describe('getApiUrl Function Tests', () => {
  let getApiUrl

  beforeEach(() => {
    // Reset mocks before each test
    mockEnv.VITE_API_BASE_URL = undefined
    mockWindowConfig.API = undefined
    vi.resetModules()
  })

  describe('URL Construction Tests', () => {
    test('should use AWS API Gateway URL as default fallback', async () => {
      const { getApiUrl } = await import('../../../config/environment')
      const result = getApiUrl('/metrics')
      
      // Should use the AWS API Gateway URL, not protrade.com
      expect(result).toBe('https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev/metrics')
      expect(result).not.toContain('api.protrade.com')
      expect(result).not.toContain('/v1/') // Should not add v1 prefix
    })

    test('should handle endpoint without leading slash', () => {
      const result = getApiUrl('metrics')
      
      expect(result).toBe('https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev/metrics')
    })

    test('should handle endpoint with leading slash', () => {
      const result = getApiUrl('/metrics')
      
      expect(result).toBe('https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev/metrics')
    })

    test('should handle complex endpoints correctly', () => {
      const endpoints = [
        '/market/overview',
        '/stocks?limit=10', 
        '/portfolio/positions',
        '/user/settings'
      ]

      endpoints.forEach(endpoint => {
        const result = getApiUrl(endpoint)
        
        expect(result).toContain('https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev')
        expect(result).not.toContain('api.protrade.com')
        expect(result).not.toContain('/v1/')
        expect(result).toEndWith(endpoint.replace(/^\//, ''))
      })
    })

    test('should use environment variable if provided', () => {
      mockEnv.VITE_API_BASE_URL = 'https://custom-api.example.com'
      
      // Re-import to pick up new env var
      vi.doUnmock('../../../config/environment')
      const { getApiUrl: customGetApiUrl } = await import('../../../config/environment')
      
      const result = customGetApiUrl('/metrics')
      expect(result).toBe('https://custom-api.example.com/metrics')
    })

    test('should use window config if provided', () => {
      mockWindowConfig.API = { BASE_URL: 'https://config-api.example.com' }
      
      // Re-import to pick up new window config
      vi.doUnmock('../../../config/environment')
      const { getApiUrl: configGetApiUrl } = await import('../../../config/environment')
      
      const result = configGetApiUrl('/metrics')
      expect(result).toBe('https://config-api.example.com/metrics')
    })
  })

  describe('DataCache Integration Tests', () => {
    test('should match exact URLs used by dataCache preloadCommonData', () => {
      const commonEndpoints = [
        { endpoint: '/market/overview', expected: 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev/market/overview' },
        { endpoint: '/stocks?limit=10', expected: 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev/stocks?limit=10' },
        { endpoint: '/metrics', expected: 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev/metrics' }
      ]

      commonEndpoints.forEach(({ endpoint, expected }) => {
        const result = getApiUrl(endpoint)
        expect(result).toBe(expected)
        
        // Critical: Must not contain protrade.com
        expect(result).not.toContain('api.protrade.com')
        expect(result).not.toContain('protrade.com')
      })
    })

    test('should handle all potential endpoint patterns from dataCache', () => {
      const endpointPatterns = [
        '',                    // Empty endpoint
        '/',                   // Root endpoint  
        '/api/status',         // Simple path
        '/portfolio/123',      // Path with ID
        '/stocks?symbol=AAPL', // Query parameters
        '/market/overview?date=2025-01-01', // Path with query
        '/user/settings#preferences'        // With hash
      ]

      endpointPatterns.forEach(endpoint => {
        const result = getApiUrl(endpoint)
        
        expect(result).toStartWith('https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev')
        expect(result).not.toContain('api.protrade.com')
        expect(result).not.toContain('undefined')
        expect(result).not.toContain('null')
      })
    })
  })

  describe('Error Prevention Tests', () => {
    test('should never return protrade.com URLs', () => {
      const testEndpoints = [
        '/metrics',
        '/market/overview', 
        '/portfolio',
        '/stocks',
        '/user',
        '/analytics',
        '/signals'
      ]

      testEndpoints.forEach(endpoint => {
        const result = getApiUrl(endpoint)
        
        // Critical security test - must never use protrade.com
        expect(result).not.toMatch(/protrade\.com/)
        expect(result).not.toMatch(/api\.protrade\.com/)
      })
    })

    test('should handle malformed endpoints gracefully', () => {
      const malformedEndpoints = [
        '//double/slash',
        'no-leading-slash',
        '/trailing/slash/',
        '/multiple//slashes',
        '/spaces in path',
        '/special@chars',
        null,
        undefined
      ]

      malformedEndpoints.forEach(endpoint => {
        expect(() => {
          const result = getApiUrl(endpoint)
          expect(result).not.toContain('api.protrade.com')
        }).not.toThrow()
      })
    })

    test('should maintain URL structure consistency', () => {
      const result = getApiUrl('/metrics')
      
      // Must follow AWS API Gateway pattern
      expect(result).toMatch(/^https:\/\/[a-z0-9]+\.execute-api\.[a-z-]+\.amazonaws\.com\/[a-z]+\//)
      
      // Must not have double slashes (except after protocol)
      const withoutProtocol = result.replace('https://', '')
      expect(withoutProtocol).not.toContain('//')
      
      // Must not end with trailing slash (unless endpoint is empty)
      if (result !== 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev/') {
        expect(result).not.toMatch(/\/$/)
      }
    })
  })

  describe('Environment-based URL Resolution', () => {
    test('should correctly prioritize configuration sources', async () => {
      // Test priority: env var > window.__CONFIG__ > default
      
      // 1. Default should be AWS API Gateway
      expect(getApiUrl('/test')).toContain('2m14opj30h.execute-api.us-east-1.amazonaws.com')
      
      // 2. Window config should override default
      mockWindowConfig.API = { BASE_URL: 'https://window-config.example.com' }
      vi.doUnmock('../../../config/environment')
      const { getApiUrl: windowGetApiUrl } = await import('../../../config/environment')
      expect(windowGetApiUrl('/test')).toContain('window-config.example.com')
      
      // 3. Environment variable should override all
      mockEnv.VITE_API_BASE_URL = 'https://env-var.example.com'
      vi.doUnmock('../../../config/environment')
      const { getApiUrl: envGetApiUrl } = await import('../../../config/environment')
      expect(envGetApiUrl('/test')).toContain('env-var.example.com')
    })
  })

  describe('Real Usage Simulation', () => {
    test('should simulate exact dataCache.js usage pattern', async () => {
      // Simulate the exact import and usage from dataCache.js
      const { getApiUrl: importedGetApiUrl } = await import('../../../config/environment')
      const fullUrl = importedGetApiUrl('/metrics')
      
      console.log(`[Test] Simulated DataCache URL: ${fullUrl}`)
      
      // This is exactly what dataCache.js does
      expect(fullUrl).toBe('https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev/metrics')
      expect(fullUrl).not.toContain('api.protrade.com')
      
      // Verify it would be a valid fetch URL
      expect(fullUrl).toMatch(/^https:\/\//)
      expect(() => new URL(fullUrl)).not.toThrow()
    })

    test('should work with all dataCache endpoints', () => {
      const dataCacheEndpoints = [
        '/market/overview',
        '/stocks?limit=10', 
        '/metrics'
      ]

      dataCacheEndpoints.forEach(endpoint => {
        const result = getApiUrl(endpoint)
        
        console.log(`[Test] DataCache endpoint ${endpoint} -> ${result}`)
        
        expect(result).toContain('https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev')
        expect(result).not.toContain('api.protrade.com')
        expect(result).not.toContain('/v1/') // Critical: no v1 prefix
        
        // Should be a valid URL for fetch()
        expect(() => new URL(result)).not.toThrow()
      })
    })
  })
})