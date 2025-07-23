/**
 * Simple getApiUrl Function Test
 * Tests the exact function used by dataCache.js - no complex mocking
 */

import { describe, test, expect } from 'vitest'
import { getApiUrl } from '../../../config/environment'

describe('getApiUrl Function - Simple Tests', () => {
  
  test('should NOT return protrade.com URLs', () => {
    const result = getApiUrl('/metrics')
    
    // Critical: Must never return protrade.com
    expect(result).not.toContain('api.protrade.com')
    expect(result).not.toContain('protrade.com')
    
    console.log('✅ getApiUrl(/metrics) =', result)
  })

  test('should return AWS API Gateway URL for metrics endpoint', () => {
    const result = getApiUrl('/metrics')
    
    // Should use AWS API Gateway
    expect(result).toContain('execute-api.us-east-1.amazonaws.com')
    expect(result).toContain('/dev/')
    
    // Should be the exact URL that dataCache.js will call
    expect(result).toBe('https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev/metrics')
  })

  test('should handle all dataCache endpoints correctly', () => {
    const dataCacheEndpoints = [
      { endpoint: '/metrics', expected: 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev/metrics' },
      { endpoint: '/market/overview', expected: 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev/market/overview' },
      { endpoint: '/stocks?limit=10', expected: 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev/stocks?limit=10' }
    ]

    dataCacheEndpoints.forEach(({ endpoint, expected }) => {
      const result = getApiUrl(endpoint)
      
      expect(result).toBe(expected)
      expect(result).not.toContain('api.protrade.com')
      
      console.log(`✅ ${endpoint} -> ${result}`)
    })
  })

  test('should create valid fetch URLs', () => {
    const endpoints = ['/metrics', '/market/overview', '/stocks']
    
    endpoints.forEach(endpoint => {
      const result = getApiUrl(endpoint)
      
      // Should be a valid URL that fetch() can use
      expect(result).toMatch(/^https:\/\//)
      expect(result).not.toContain('api.protrade.com')
      expect(result.length).toBeGreaterThan(20)
    })
  })

  test('should match exact dataCache.js import and usage', () => {
    // This simulates exactly: const { getApiUrl } = await import('../config/environment');
    const fullUrl = getApiUrl('/metrics')
    
    // This is what gets passed to fetch() in dataCache.js line 192
    console.log('[DataCache Simulation] Fetching', fullUrl)
    
    expect(fullUrl).toBe('https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev/metrics')
    expect(fullUrl).not.toContain('api.protrade.com')
    
    // Should be exactly what dataCache.js will use
    expect(typeof fullUrl).toBe('string')
    expect(fullUrl.length).toBeGreaterThan(0)
  })
})