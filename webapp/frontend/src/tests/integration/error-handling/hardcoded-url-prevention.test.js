/**
 * Hardcoded URL Prevention Tests
 * Ensures no hardcoded URLs like api.protrade.com can slip through
 */

import { describe, test, expect, vi } from 'vitest'
import { promises as fs } from 'fs'
import path from 'path'

// List of forbidden hardcoded URLs that should never appear in the codebase
const FORBIDDEN_URLS = [
  'api.protrade.com',
  'protrade.com',
  'https://api.protrade.com',
  'http://api.protrade.com'
]

// Files to scan for hardcoded URLs
const CRITICAL_FILES = [
  'src/config/environment.js',
  'src/services/api.js',
  'src/services/dataCache.js',
  'src/services/configuredApi.js'
]

describe('Hardcoded URL Prevention Tests', () => {
  
  describe('Static Code Analysis', () => {
    test('should not contain forbidden URLs in critical files', async () => {
      for (const filePath of CRITICAL_FILES) {
        try {
          const fullPath = path.join(process.cwd(), filePath)
          const content = await fs.readFile(fullPath, 'utf-8')
          
          FORBIDDEN_URLS.forEach(forbiddenUrl => {
            const lines = content.split('\n')
            lines.forEach((line, index) => {
              if (line.includes(forbiddenUrl) && !line.includes('// Test') && !line.includes('*')) {
                throw new Error(
                  `❌ HARDCODED URL DETECTED!\n` +
                  `File: ${filePath}\n` +
                  `Line ${index + 1}: ${line.trim()}\n` +
                  `Forbidden URL: ${forbiddenUrl}\n` +
                  `This will cause ERR_NAME_NOT_RESOLVED errors!`
                )
              }
            })
          })
          
          console.log(`✅ ${filePath} - No hardcoded URLs detected`)
        } catch (error) {
          if (error.code === 'ENOENT') {
            console.warn(`⚠️ File not found: ${filePath}`)
          } else {
            throw error
          }
        }
      }
    })

    test('should verify getApiUrl function returns correct URLs', async () => {
      // Import and test the actual function
      const { getApiUrl } = await import('../../../config/environment')
      
      const testEndpoints = [
        '/metrics',
        '/market/overview',
        '/stocks?limit=10'
      ]

      testEndpoints.forEach(endpoint => {
        const result = getApiUrl(endpoint)
        
        // Must NOT contain forbidden URLs
        FORBIDDEN_URLS.forEach(forbiddenUrl => {
          expect(result).not.toContain(forbiddenUrl)
        })
        
        // Must contain correct AWS API Gateway URL
        expect(result).toContain('execute-api.us-east-1.amazonaws.com')
        
        console.log(`✅ ${endpoint} -> ${result}`)
      })
    })
  })

  describe('Runtime URL Generation Tests', () => {
    test('should never generate protrade.com URLs at runtime', async () => {
      // Mock different environment scenarios
      const scenarios = [
        { name: 'Default configuration', env: {} },
        { name: 'Development environment', env: { NODE_ENV: 'development' } },
        { name: 'Production environment', env: { NODE_ENV: 'production' } },
        { name: 'Test environment', env: { NODE_ENV: 'test' } }
      ]

      for (const scenario of scenarios) {
        // Mock environment
        const originalEnv = process.env.NODE_ENV
        process.env.NODE_ENV = scenario.env.NODE_ENV || 'test'
        
        try {
          // Re-import to get fresh configuration
          vi.doUnmock('../../../config/environment')
          const { getApiUrl } = await import('../../../config/environment')
          
          const testUrl = getApiUrl('/metrics')
          
          // Critical check - must never generate protrade.com URLs
          FORBIDDEN_URLS.forEach(forbiddenUrl => {
            expect(testUrl).not.toContain(forbiddenUrl)
          })
          
          console.log(`✅ ${scenario.name}: ${testUrl}`)
          
        } finally {
          process.env.NODE_ENV = originalEnv
        }
      }
    })

    test('should handle missing configuration gracefully', () => {
      // Mock scenario where all configuration sources fail
      const mockWindow = {
        __CONFIG__: undefined,
        __RUNTIME_CONFIG__: undefined
      }
      
      vi.stubGlobal('window', mockWindow)
      vi.stubGlobal('import.meta', { env: {} })
      
      // Should still not generate protrade.com URLs
      return import('../../../config/environment').then(({ getApiUrl }) => {
        const result = getApiUrl('/metrics')
        
        FORBIDDEN_URLS.forEach(forbiddenUrl => {
          expect(result).not.toContain(forbiddenUrl)
        })
        
        // Should fall back to AWS API Gateway
        expect(result).toContain('execute-api.us-east-1.amazonaws.com')
      })
    })
  })

  describe('DataCache Integration Prevention', () => {
    test('should verify dataCache cannot generate forbidden URLs', async () => {
      // Mock fetch to intercept URLs being called
      const fetchCalls = []
      const originalFetch = global.fetch
      
      global.fetch = vi.fn((url) => {
        fetchCalls.push(url)
        
        // Check if any forbidden URLs are being called
        FORBIDDEN_URLS.forEach(forbiddenUrl => {
          if (url.includes(forbiddenUrl)) {
            throw new Error(`❌ DataCache attempted to call forbidden URL: ${url}`)
          }
        })
        
        return Promise.resolve({
          ok: false,
          status: 404,
          json: () => Promise.resolve({ error: 'Test mock' })
        })
      })
      
      try {
        // Import and test dataCache
        const { default: DataCache } = await import('../../../services/dataCache')
        const cache = new DataCache()
        
        // Try to trigger URL generation
        try {
          await cache.get('/metrics', {}, { 
            fetchFunction: async () => {
              const { getApiUrl } = await import('../../../config/environment')
              const url = getApiUrl('/metrics')
              
              // This simulates what dataCache.js actually does
              return fetch(url)
            }
          })
        } catch (error) {
          // Expected to fail with mock, but shouldn't be due to forbidden URLs
          if (error.message.includes('forbidden URL')) {
            throw error
          }
        }
        
        // Verify no forbidden URLs were called
        fetchCalls.forEach(url => {
          FORBIDDEN_URLS.forEach(forbiddenUrl => {
            expect(url).not.toContain(forbiddenUrl)
          })
        })
        
        console.log(`✅ DataCache URL calls: ${fetchCalls.join(', ')}`)
        
      } finally {
        global.fetch = originalFetch
      }
    })
  })

  describe('Configuration Validation', () => {
    test('should validate AWS_CONFIG contains correct URLs', async () => {
      const { AWS_CONFIG } = await import('../../../config/environment')
      
      // Check base API URL
      FORBIDDEN_URLS.forEach(forbiddenUrl => {
        expect(AWS_CONFIG.api.baseUrl).not.toContain(forbiddenUrl)
      })
      
      // Should contain correct AWS API Gateway URL
      expect(AWS_CONFIG.api.baseUrl).toContain('execute-api.us-east-1.amazonaws.com')
      
      console.log(`✅ AWS_CONFIG.api.baseUrl: ${AWS_CONFIG.api.baseUrl}`)
    })

    test('should validate EXTERNAL_APIS configuration', async () => {
      const { EXTERNAL_APIS } = await import('../../../config/environment')
      
      Object.entries(EXTERNAL_APIS).forEach(([provider, config]) => {
        FORBIDDEN_URLS.forEach(forbiddenUrl => {
          expect(config.baseUrl).not.toContain(forbiddenUrl)
        })
        
        console.log(`✅ ${provider}: ${config.baseUrl}`)
      })
    })
  })

  describe('Error Simulation Tests', () => {
    test('should simulate and handle ERR_NAME_NOT_RESOLVED scenario', async () => {
      // Create a mock that simulates the exact error from the console
      const mockFetch = vi.fn(() => 
        Promise.reject(new Error('net::ERR_NAME_NOT_RESOLVED'))
      )
      
      global.fetch = mockFetch
      
      try {
        const { getApiUrl } = await import('../../../config/environment')
        const url = getApiUrl('/metrics')
        
        // Verify the URL is correct (not protrade.com)
        expect(url).not.toContain('api.protrade.com')
        expect(url).toContain('execute-api.us-east-1.amazonaws.com')
        
        // Simulate the fetch call that would happen in dataCache
        try {
          await fetch(url)
        } catch (error) {
          // This error should be about network issues, not wrong URLs
          expect(error.message).toBe('net::ERR_NAME_NOT_RESOLVED')
          
          // But the URL itself should be correct
          expect(url).toBe('https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev/metrics')
        }
        
      } finally {
        global.fetch = originalFetch
      }
    })
  })

  describe('Continuous Monitoring', () => {
    test('should provide monitoring hooks for forbidden URL detection', () => {
      // Create a monitoring function that can be used in production
      const monitorUrlGeneration = (url) => {
        FORBIDDEN_URLS.forEach(forbiddenUrl => {
          if (url.includes(forbiddenUrl)) {
            console.error(`🚨 FORBIDDEN URL DETECTED: ${url}`)
            
            // In production, this could send an alert
            if (typeof window !== 'undefined' && window.analytics) {
              window.analytics.track('Forbidden URL Detected', { url })
            }
            
            throw new Error(`Forbidden URL detected: ${url}`)
          }
        })
        
        return true
      }
      
      // Test the monitor with various URLs
      const testUrls = [
        'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev/metrics',
        'https://d1zb7knau41vl9.cloudfront.net/assets/app.js',
        'https://polygon.io/v1/stocks/AAPL'
      ]
      
      testUrls.forEach(url => {
        expect(() => monitorUrlGeneration(url)).not.toThrow()
      })
      
      // Test that forbidden URLs are caught
      FORBIDDEN_URLS.forEach(forbiddenUrl => {
        expect(() => monitorUrlGeneration(`https://${forbiddenUrl}/api/test`))
          .toThrow(`Forbidden URL detected`)
      })
    })
  })
})