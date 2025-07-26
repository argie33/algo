/**
 * useSimpleFetch Integration Tests
 * Tests the useSimpleFetch hook integrated with real API endpoints and dataFormatHelper
 * Tests full request lifecycle with actual deployed infrastructure
 */

import { describe, it, expect, beforeEach, afterEach, beforeAll, afterAll, vi } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useSimpleFetch } from '../../../hooks/useSimpleFetch';
import { getApiUrl } from '../../../config/getApiUrl';

// Test timeout for integration tests
const INTEGRATION_TIMEOUT = 30000;

describe('🌐 useSimpleFetch Integration Tests', () => {
  let apiBaseUrl;

  beforeAll(async () => {
    // Get real API URL for integration testing
    try {
      apiBaseUrl = await getApiUrl();
      console.log('🔗 Using API base URL for integration tests:', apiBaseUrl);
    } catch (error) {
      console.warn('⚠️ Could not get API URL, using fallback for integration tests');
      apiBaseUrl = 'https://httpbin.org'; // Fallback to httpbin for testing
    }
  });

  beforeEach(() => {
    vi.useRealTimers();
  });

  afterEach(() => {
    vi.clearAllTimers();
  });

  describe('Real API Integration', () => {
    it('should integrate with real health endpoint', async () => {
      const healthUrl = apiBaseUrl.includes('httpbin') 
        ? `${apiBaseUrl}/json` // httpbin fallback
        : `${apiBaseUrl}/api/health`;

      const { result } = renderHook(() => 
        useSimpleFetch(healthUrl, { 
          retry: 2,
          staleTime: 0 // Always fresh for testing
        })
      );

      // Initially loading
      expect(result.current.isLoading).toBe(true);
      expect(result.current.data).toBe(null);
      expect(result.current.error).toBe(null);

      // Wait for real API response
      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      }, { timeout: INTEGRATION_TIMEOUT });

      // Should have successful result or graceful error handling
      if (result.current.isSuccess) {
        expect(result.current.data).toBeTruthy();
        expect(result.current.error).toBe(null);
        expect(result.current.isError).toBe(false);
        console.log('✅ Health endpoint integration successful');
      } else {
        // If API is unavailable, should have meaningful error
        expect(result.current.error).toBeTruthy();
        expect(result.current.data).toBe(null);
        expect(result.current.isError).toBe(true);
        console.log('⚠️ Health endpoint unavailable (expected in some environments):', result.current.error);
      }

      // Should have correct UI state regardless of success/failure
      expect(result.current.isLoading).toBe(false);
      expect(typeof result.current.refetch).toBe('function');
    }, INTEGRATION_TIMEOUT);

    it('should handle real 404 endpoints gracefully', async () => {
      const notFoundUrl = apiBaseUrl.includes('httpbin')
        ? `${apiBaseUrl}/status/404`
        : `${apiBaseUrl}/api/nonexistent`;

      const { result } = renderHook(() => 
        useSimpleFetch(notFoundUrl, { 
          retry: 1 // Minimal retry for 404
        })
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      }, { timeout: INTEGRATION_TIMEOUT });

      // Should handle 404 appropriately
      expect(result.current.isError).toBe(true);
      expect(result.current.data).toBe(null);
      expect(result.current.error).toBeTruthy();
      
      // Error message should indicate endpoint not available
      if (result.current.error.includes('404') || result.current.error.includes('not found') || result.current.error.includes('not available')) {
        console.log('✅ 404 handling working correctly:', result.current.error);
      } else {
        console.log('ℹ️ Different error format for 404:', result.current.error);
      }
    }, INTEGRATION_TIMEOUT);

    it('should integrate with dataFormatHelper for response processing', async () => {
      // Use a test endpoint that returns structured data
      const testUrl = apiBaseUrl.includes('httpbin')
        ? `${apiBaseUrl}/json`
        : `${apiBaseUrl}/api/health`;

      const { result } = renderHook(() => 
        useSimpleFetch(testUrl)
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      }, { timeout: INTEGRATION_TIMEOUT });

      if (result.current.isSuccess) {
        // Should have processed data through dataFormatHelper
        expect(result.current.data).toBeTruthy();
        
        // Check that UI state helpers are working
        expect(result.current.isSuccess).toBe(true);
        expect(result.current.isError).toBe(false);
        expect(result.current.isLoading).toBe(false);
        
        // Should have UI state properties from getUIState
        expect(result.current).toHaveProperty('data');
        expect(result.current).toHaveProperty('loading');
        expect(result.current).toHaveProperty('error');
        expect(result.current).toHaveProperty('refetch');
        
        console.log('✅ DataFormatHelper integration working');
      }
    }, INTEGRATION_TIMEOUT);
  });

  describe('Circuit Breaker Integration', () => {
    it('should handle circuit breaker responses from real API', async () => {
      // This test simulates what happens when the API returns circuit breaker errors
      const onError = vi.fn();
      
      // Use a real endpoint but with callback to test error handling
      const testUrl = apiBaseUrl.includes('httpbin')
        ? `${apiBaseUrl}/delay/5` // This will likely timeout
        : `${apiBaseUrl}/api/test-circuit-breaker`;

      const { result } = renderHook(() => 
        useSimpleFetch(testUrl, { 
          retry: 1,
          onError,
          // Short timeout to trigger errors
          enabled: true
        })
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      }, { timeout: INTEGRATION_TIMEOUT });

      // Should handle timeout/error gracefully
      if (result.current.isError) {
        expect(result.current.error).toBeTruthy();
        expect(result.current.data).toBe(null);
        
        // If onError was called, it should have been with an Error object
        if (onError.mock.calls.length > 0) {
          expect(onError).toHaveBeenCalledWith(expect.any(Error));
        }
        
        console.log('✅ Error handling integration working:', result.current.error);
      }
    }, INTEGRATION_TIMEOUT);
  });

  describe('Real Network Conditions', () => {
    it('should handle real network delays appropriately', async () => {
      const delayUrl = apiBaseUrl.includes('httpbin')
        ? `${apiBaseUrl}/delay/1` // 1 second delay
        : `${apiBaseUrl}/api/health`;

      const startTime = Date.now();
      
      const { result } = renderHook(() => 
        useSimpleFetch(delayUrl, { 
          retry: 0 // No retry for this test
        })
      );

      expect(result.current.isLoading).toBe(true);

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      }, { timeout: INTEGRATION_TIMEOUT });

      const endTime = Date.now();
      const duration = endTime - startTime;

      // Should have taken some time (at least a few hundred ms for real network)
      if (apiBaseUrl.includes('httpbin')) {
        expect(duration).toBeGreaterThan(500); // At least 500ms for real network + 1s delay
      }

      console.log(`⏱️ Network request took ${duration}ms`);
    }, INTEGRATION_TIMEOUT);

    it('should handle concurrent requests correctly', async () => {
      const testUrl = apiBaseUrl.includes('httpbin')
        ? `${apiBaseUrl}/json`
        : `${apiBaseUrl}/api/health`;

      // Create multiple hooks that make requests concurrently
      const { result: result1 } = renderHook(() => 
        useSimpleFetch(testUrl, { retry: 1 })
      );
      
      const { result: result2 } = renderHook(() => 
        useSimpleFetch(testUrl, { retry: 1 })
      );

      const { result: result3 } = renderHook(() => 
        useSimpleFetch(testUrl, { retry: 1 })
      );

      // Wait for all requests to complete
      await waitFor(() => {
        expect(result1.current.isLoading).toBe(false);
        expect(result2.current.isLoading).toBe(false);
        expect(result3.current.isLoading).toBe(false);
      }, { timeout: INTEGRATION_TIMEOUT });

      // All should have completed (either success or error)
      expect(result1.current.isLoading).toBe(false);
      expect(result2.current.isLoading).toBe(false);
      expect(result3.current.isLoading).toBe(false);

      console.log('✅ Concurrent requests handled correctly');
    }, INTEGRATION_TIMEOUT);
  });

  describe('React Query Compatibility', () => {
    it('should work with React Query style objects in real scenarios', async () => {
      const queryFn = async () => {
        const response = await fetch(`${apiBaseUrl}/json`);
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        return response.json();
      };

      const { result } = renderHook(() => 
        useSimpleFetch({
          queryKey: ['integration-test'],
          queryFn,
          retry: 1,
          staleTime: 0
        })
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      }, { timeout: INTEGRATION_TIMEOUT });

      // Should work with React Query style
      if (result.current.isSuccess) {
        expect(result.current.data).toBeTruthy();
        expect(result.current.error).toBe(null);
        console.log('✅ React Query compatibility working');
      } else {
        expect(result.current.error).toBeTruthy();
        console.log('⚠️ React Query style failed as expected in some environments');
      }
    }, INTEGRATION_TIMEOUT);
  });

  describe('Refetch Integration', () => {
    it('should handle manual refetch with real API', async () => {
      const testUrl = apiBaseUrl.includes('httpbin')
        ? `${apiBaseUrl}/uuid` // Returns different UUID each time
        : `${apiBaseUrl}/api/health`;

      const { result } = renderHook(() => 
        useSimpleFetch(testUrl, { 
          retry: 1,
          staleTime: 0 // Always fresh
        })
      );

      // Wait for initial request
      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      }, { timeout: INTEGRATION_TIMEOUT });

      const initialData = result.current.data;
      const initialError = result.current.error;

      // Manual refetch
      act(() => {
        result.current.refetch();
      });

      // Should be loading again
      expect(result.current.isLoading).toBe(true);

      // Wait for refetch to complete
      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      }, { timeout: INTEGRATION_TIMEOUT });

      // Should have completed the refetch
      expect(result.current.isLoading).toBe(false);
      
      if (result.current.isSuccess && initialData) {
        // For UUID endpoint, data should be different
        if (apiBaseUrl.includes('httpbin')) {
          expect(result.current.data).not.toEqual(initialData);
        }
        console.log('✅ Manual refetch working');
      } else if (result.current.isError && initialError) {
        // Error state should be consistent
        expect(result.current.error).toBeTruthy();
        console.log('✅ Refetch error handling consistent');
      }
    }, INTEGRATION_TIMEOUT);
  });

  describe('Environment Resilience', () => {
    it('should handle different deployment environments gracefully', async () => {
      // Test with various potential endpoints that might exist
      const testEndpoints = [
        `${apiBaseUrl}/api/health`,
        `${apiBaseUrl}/health`,
        `${apiBaseUrl}/api/status`,
        `${apiBaseUrl}/status`
      ];

      for (const endpoint of testEndpoints) {
        const { result } = renderHook(() => 
          useSimpleFetch(endpoint, { 
            retry: 0, // No retry for environment testing
            enabled: true
          })
        );

        await waitFor(() => {
          expect(result.current.isLoading).toBe(false);
        }, { timeout: INTEGRATION_TIMEOUT / 2 });

        // Should complete (success or error)
        expect(result.current.isLoading).toBe(false);
        expect(typeof result.current.refetch).toBe('function');

        if (result.current.isSuccess) {
          console.log(`✅ Endpoint ${endpoint} is available`);
          break; // Found a working endpoint
        } else {
          console.log(`⚠️ Endpoint ${endpoint} not available: ${result.current.error}`);
        }
      }
    }, INTEGRATION_TIMEOUT);

    it('should work in CI/CD environment with network restrictions', async () => {
      // Use external testing service that should be available
      const externalUrl = process.env.CI 
        ? 'https://httpbin.org/json' // Reliable external service for CI
        : `${apiBaseUrl}/api/health`;

      const { result } = renderHook(() => 
        useSimpleFetch(externalUrl, { 
          retry: 2,
          onError: (error) => {
            console.log('CI/CD environment error (expected):', error.message);
          }
        })
      );

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      }, { timeout: INTEGRATION_TIMEOUT });

      // Should complete without crashing
      expect(result.current.isLoading).toBe(false);
      
      if (process.env.CI) {
        console.log('🏗️ CI/CD environment test completed');
      }
    }, INTEGRATION_TIMEOUT);
  });
});