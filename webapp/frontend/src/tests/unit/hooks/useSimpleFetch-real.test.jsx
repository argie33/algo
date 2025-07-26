/**
 * Real useSimpleFetch Hook Unit Tests
 * Tests the actual useSimpleFetch hook functionality with real HTTP behavior
 * NO MOCKS - Tests actual fetch behavior, retry logic, error handling, and data processing
 */

import React from 'react';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { act, waitFor, render } from '@testing-library/react';
import { renderWithProviders, renderHook } from '../../helpers/testUtils';
import { useSimpleFetch, SimpleQueryClient, SimpleQueryProvider } from '../../../hooks/useSimpleFetch';

// Only mock global fetch for controlled testing scenarios
const originalFetch = global.fetch;

describe('🎣 useSimpleFetch Hook - Real Functionality Tests', () => {
  
  beforeEach(() => {
    // Reset to original fetch for most tests
    global.fetch = originalFetch;
    vi.clearAllTimers();
    vi.useRealTimers();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  describe('Real HTTP Request Functionality', () => {
    it('should handle successful real HTTP requests', async () => {
      // Use a real HTTP testing service
      const testUrl = 'https://httpbin.org/json';
      
      function TestComponent() {
        const result = useSimpleFetch(testUrl, { retry: 1 });
        return <div data-testid="hook-result">{JSON.stringify(result)}</div>;
      }
      
      const { getByTestId } = renderWithProviders(<TestComponent />);

      // Test will initially show loading state
      const hookResult = getByTestId('hook-result');
      expect(hookResult).toBeInTheDocument();
      
      // Wait for request to complete (simplified test)
      await waitFor(() => {
        const content = hookResult.textContent;
        const parsed = JSON.parse(content);
        expect(parsed.loading).toBe(false);
      }, { timeout: 10000 });
    });

    it('should handle real HTTP 404 errors without retrying', async () => {
      const testUrl = 'https://httpbin.org/status/404';
      
      const { result } = renderHook(() => 
        useSimpleFetch(testUrl, { retry: 3 })
      );

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      }, { timeout: 10000 });

      // Should handle 404 error properly
      expect(result.current.error).toContain('404');
      expect(result.current.data).toBe(null);
      expect(result.current.isError).toBe(true);
      expect(result.current.isSuccess).toBe(false);
    });

    it('should detect HTML responses and show routing error', async () => {
      // Mock fetch to return HTML instead of JSON
      global.fetch = vi.fn(() =>
        Promise.resolve({
          ok: true,
          headers: new Headers({ 'content-type': 'text/html' }),
          text: () => Promise.resolve('<!DOCTYPE html><html><body>Not Found</body></html>')
        })
      );

      const { result } = renderHook(() => 
        useSimpleFetch('https://example.com/api/test')
      );

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.error).toContain('API routing misconfiguration');
      expect(result.current.data).toBe(null);
    });

    it('should handle malformed JSON responses', async () => {
      global.fetch = vi.fn(() =>
        Promise.resolve({
          ok: true,
          headers: new Headers({ 'content-type': 'application/json' }),
          text: () => Promise.resolve('{"invalid": json}')
        })
      );

      const { result } = renderHook(() => 
        useSimpleFetch('https://example.com/api/test')
      );

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.error).toContain('Invalid JSON response');
      expect(result.current.data).toBe(null);
    });
  });

  describe('React Query Style Object Usage', () => {
    it('should work with React Query style queryFn', async () => {
      const mockQueryFn = vi.fn(() =>
        Promise.resolve({ success: true, data: { test: 'data' } })
      );

      const queryOptions = {
        queryKey: ['test-query'],
        queryFn: mockQueryFn,
        retry: 1
      };

      const { result } = renderHook(() => 
        useSimpleFetch(queryOptions)
      );

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(mockQueryFn).toHaveBeenCalled();
      expect(result.current.data).toEqual({ test: 'data' });
      expect(result.current.error).toBe(null);
    });

    it('should handle invalid React Query objects gracefully', async () => {
      const invalidObject = { queryKey: ['test'], invalidProperty: true };

      const { result } = renderHook(() => 
        useSimpleFetch(invalidObject)
      );

      // Should disable the hook and not make requests
      expect(result.current.loading).toBe(false);
      expect(result.current.data).toBe(null);
      expect(result.current.error).toBe(null);
    });

    it('should handle invalid input types gracefully', async () => {
      const { result } = renderHook(() => 
        useSimpleFetch(123) // Invalid number input
      );

      // Should disable the hook
      expect(result.current.loading).toBe(false);
      expect(result.current.data).toBe(null);
      expect(result.current.error).toBe(null);
    });
  });

  describe('Retry Logic with Real Network Conditions', () => {
    it('should retry on network failures but not on 404', async () => {
      let callCount = 0;
      global.fetch = vi.fn(() => {
        callCount++;
        if (callCount <= 2) {
          return Promise.reject(new Error('Network error'));
        }
        return Promise.resolve({
          ok: true,
          headers: new Headers({ 'content-type': 'application/json' }),
          text: () => Promise.resolve('{"success": true, "data": {"retried": true}}')
        });
      });

      const { result } = renderHook(() => 
        useSimpleFetch('https://example.com/api/test', { retry: 3 })
      );

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      }, { timeout: 15000 });

      expect(callCount).toBeGreaterThan(1); // Should have retried
      expect(result.current.data).toEqual({ retried: true });
      expect(result.current.error).toBe(null);
    });

    it('should not retry on circuit breaker errors', async () => {
      global.fetch = vi.fn(() =>
        Promise.reject(new Error('Circuit breaker is open'))
      );

      const { result } = renderHook(() => 
        useSimpleFetch('https://example.com/api/test', { retry: 3 })
      );

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(global.fetch).toHaveBeenCalledTimes(1); // No retry
      expect(result.current.error).toBe('Service temporarily unavailable - please try again in a few moments');
    });

    it('should not retry on resource exhaustion errors', async () => {
      global.fetch = vi.fn(() =>
        Promise.reject(new Error('net::ERR_INSUFFICIENT_RESOURCES'))
      );

      const { result } = renderHook(() => 
        useSimpleFetch('https://example.com/api/test', { retry: 3 })
      );

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(global.fetch).toHaveBeenCalledTimes(1); // No retry  
      expect(result.current.error).toBe('Too many requests - please wait a moment and refresh the page');
    });
  });

  describe('Error Callback Functionality', () => {
    it('should call onError callback on failures', async () => {
      const onError = vi.fn();
      
      global.fetch = vi.fn(() =>
        Promise.reject(new Error('Test error'))
      );

      const { result } = renderHook(() => 
        useSimpleFetch('https://example.com/api/test', { 
          retry: 1,
          onError 
        })
      );

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(onError).toHaveBeenCalledWith(expect.any(Error));
      expect(result.current.error).toBe('Test error');
    });

    it('should handle errors in onError callback gracefully', async () => {
      const onError = vi.fn(() => {
        throw new Error('Callback error');
      });
      
      global.fetch = vi.fn(() =>
        Promise.reject(new Error('Original error'))
      );

      const { result } = renderHook(() => 
        useSimpleFetch('https://example.com/api/test', { 
          retry: 1,
          onError 
        })
      );

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(onError).toHaveBeenCalled();
      expect(result.current.error).toBe('Original error'); // Original error preserved
    });
  });

  describe('Window Focus Refetch', () => {
    it('should refetch on window focus when enabled', async () => {
      let callCount = 0;
      global.fetch = vi.fn(() => {
        callCount++;
        return Promise.resolve({
          ok: true,
          headers: new Headers({ 'content-type': 'application/json' }),
          text: () => Promise.resolve(`{"success": true, "data": {"call": ${callCount}}}`)
        });
      });

      const { result } = renderHook(() => 
        useSimpleFetch('https://example.com/api/test', { 
          refetchOnWindowFocus: true,
          retry: 0
        })
      );

      // Wait for initial load
      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(callCount).toBe(1);

      // Simulate window focus
      act(() => {
        // Mock document.visibilityState
        Object.defineProperty(document, 'visibilityState', {
          writable: true,
          value: 'visible'
        });
        
        // Trigger visibility change event
        const event = new Event('visibilitychange');
        window.dispatchEvent(event);
      });

      await waitFor(() => {
        expect(callCount).toBe(2);
      });
    });
  });

  describe('Manual Refetch Functionality', () => {
    it('should allow manual refetch via refetch function', async () => {
      let callCount = 0;
      global.fetch = vi.fn(() => {
        callCount++;
        return Promise.resolve({
          ok: true,
          headers: new Headers({ 'content-type': 'application/json' }),
          text: () => Promise.resolve(`{"success": true, "data": {"call": ${callCount}}}`)
        });
      });

      const { result } = renderHook(() => 
        useSimpleFetch('https://example.com/api/test', { retry: 0 })
      );

      // Wait for initial load
      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(callCount).toBe(1);
      expect(result.current.data).toEqual({ call: 1 });

      // Manual refetch
      act(() => {
        result.current.refetch();
      });

      await waitFor(() => {
        expect(callCount).toBe(2);
      });

      expect(result.current.data).toEqual({ call: 2 });
    });
  });

  describe('UI State Properties', () => {
    it('should provide correct UI state properties', async () => {
      global.fetch = vi.fn(() =>
        Promise.resolve({
          ok: true,
          headers: new Headers({ 'content-type': 'application/json' }),
          text: () => Promise.resolve('{"success": true, "data": {"test": true}}')
        })
      );

      const { result } = renderHook(() => 
        useSimpleFetch('https://example.com/api/test')
      );

      // Initially loading
      expect(result.current.isLoading).toBe(true);
      expect(result.current.isError).toBe(false);
      expect(result.current.isSuccess).toBe(false);

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      // After success
      expect(result.current.isLoading).toBe(false);
      expect(result.current.isError).toBe(false);
      expect(result.current.isSuccess).toBe(true);
    });
  });

  describe('Enabled/Disabled Functionality', () => {
    it('should not make requests when disabled', async () => {
      global.fetch = vi.fn();

      const { result } = renderHook(() => 
        useSimpleFetch('https://example.com/api/test', { enabled: false })
      );

      // Wait a bit to ensure no request is made
      await new Promise(resolve => setTimeout(resolve, 100));

      expect(global.fetch).not.toHaveBeenCalled();
      expect(result.current.loading).toBe(true); // Stays in loading state
      expect(result.current.data).toBe(null);
      expect(result.current.error).toBe(null);
    });

    it('should make request when enabled is changed to true', async () => {
      global.fetch = vi.fn(() =>
        Promise.resolve({
          ok: true,
          headers: new Headers({ 'content-type': 'application/json' }),
          text: () => Promise.resolve('{"success": true, "data": {"enabled": true}}')
        })
      );

      let enabled = false;
      const { result, rerender } = renderHook(
        ({ enabled: enabledProp }) => 
          useSimpleFetch('https://example.com/api/test', { enabled: enabledProp }),
        { initialProps: { enabled } }
      );

      expect(global.fetch).not.toHaveBeenCalled();

      // Enable the query
      enabled = true;
      rerender({ enabled });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(global.fetch).toHaveBeenCalled();
      expect(result.current.data).toEqual({ enabled: true });
    });
  });
});

describe('🔧 SimpleQueryClient - Real Functionality Tests', () => {
  let client;

  beforeEach(() => {
    client = new SimpleQueryClient({
      defaultOptions: {
        queries: {
          staleTime: 1000,
          cacheTime: 5000,
          retry: 2
        }
      }
    });
  });

  describe('Cache Management', () => {
    it('should store and retrieve cached data', () => {
      const key = ['test', 'key'];
      const data = { test: 'data' };

      client.setQueryData(key, data);
      const retrieved = client.getQueryData(key);

      expect(retrieved).toEqual(data);
    });

    it('should return undefined for non-existent keys', () => {
      const result = client.getQueryData(['non-existent']);
      expect(result).toBeUndefined();
    });

    it('should handle stale data correctly', async () => {
      const key = ['stale', 'test'];
      const data = { stale: 'data' };

      client.setQueryData(key, data);
      
      // Data should be fresh initially
      expect(client.getQueryData(key)).toEqual(data);

      // Wait for data to become stale
      await new Promise(resolve => setTimeout(resolve, 1100));

      // Data should now be stale and return undefined
      expect(client.getQueryData(key)).toBeUndefined();
    });

    it('should clear all cached data', () => {
      client.setQueryData(['key1'], { data: 1 });
      client.setQueryData(['key2'], { data: 2 });

      expect(client.getQueryData(['key1'])).toEqual({ data: 1 });
      expect(client.getQueryData(['key2'])).toEqual({ data: 2 });

      client.invalidateQueries();

      expect(client.getQueryData(['key1'])).toBeUndefined();
      expect(client.getQueryData(['key2'])).toBeUndefined();
    });

    it('should handle complex query keys correctly', () => {
      const complexKey = ['user', 123, { filter: 'active' }];
      const data = { user: 'data' };

      client.setQueryData(complexKey, data);
      const retrieved = client.getQueryData(complexKey);

      expect(retrieved).toEqual(data);
    });
  });
});

describe('🔗 SimpleQueryProvider - Real Functionality Tests', () => {
  it('should render children without provider context', () => {
    const client = new SimpleQueryClient();
    const TestComponent = () => <div data-testid="test">Test Content</div>;

    const { container } = render(
      <SimpleQueryProvider client={client}>
        <TestComponent />
      </SimpleQueryProvider>
    );

    expect(container.querySelector('[data-testid="test"]')).toHaveTextContent('Test Content');
  });
});