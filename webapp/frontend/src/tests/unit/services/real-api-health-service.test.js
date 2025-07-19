/**
 * Real API Health Service Unit Tests
 * Testing the actual apiHealthService.js with health monitoring, circuit breaker, and fallback strategies
 * CRITICAL COMPONENT - Known to have health monitoring and circuit breaker issues
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Mock fetch globally
global.fetch = vi.fn();

// Mock AbortSignal.timeout
Object.defineProperty(global.AbortSignal, 'timeout', {
  value: vi.fn((timeout) => ({
    aborted: false,
    timeout
  })),
  writable: true
});

// Mock process.env
Object.defineProperty(process, 'env', {
  value: { NODE_ENV: 'test' },
  writable: true
});

// Import the REAL ApiHealthService
import apiHealthService from '../../../services/apiHealthService';

describe('🏥 Real API Health Service', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    
    // Reset service state
    apiHealthService.stopMonitoring();
    apiHealthService.healthStatus = {
      overall: 'unknown',
      endpoints: new Map(),
      lastCheck: null,
      consecutiveFailures: 0,
      circuitBreakerOpen: false
    };
    apiHealthService.subscribers.clear();
    
    // Mock successful fetch by default
    global.fetch.mockResolvedValue({
      ok: true,
      status: 200,
      headers: {
        get: vi.fn(() => 'application/json')
      },
      json: vi.fn().mockResolvedValue({ status: 'healthy' })
    });

    // Mock console to avoid noise
    vi.spyOn(console, 'log').mockImplementation(() => {});
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
    vi.restoreAllMocks();
    apiHealthService.stopMonitoring();
  });

  describe('Service Initialization', () => {
    it('should initialize with correct default configuration', () => {
      expect(apiHealthService.config).toEqual({
        healthCheckInterval: 30000,
        circuitBreakerThreshold: 3,
        circuitBreakerTimeout: 60000,
        endpointTimeout: 5000,
        retryAttempts: 2
      });
      
      expect(apiHealthService.healthStatus.overall).toBe('unknown');
      expect(apiHealthService.healthStatus.endpoints).toBeInstanceOf(Map);
      expect(apiHealthService.healthStatus.circuitBreakerOpen).toBe(false);
      expect(apiHealthService.monitoringActive).toBe(false);
    });

    it('should initialize with empty subscribers', () => {
      expect(apiHealthService.subscribers).toBeInstanceOf(Set);
      expect(apiHealthService.subscribers.size).toBe(0);
    });
  });

  describe('Monitoring Lifecycle', () => {
    it('should start monitoring and perform initial health check', async () => {
      apiHealthService.startMonitoring();
      
      expect(apiHealthService.monitoringActive).toBe(true);
      expect(apiHealthService.healthCheckTimer).not.toBeNull();
      
      // Wait for initial health check
      await vi.advanceTimersByTimeAsync(1000);
      
      expect(global.fetch).toHaveBeenCalled();
    });

    it('should not start monitoring if already active', () => {
      apiHealthService.monitoringActive = true;
      
      const initialTimer = apiHealthService.healthCheckTimer;
      apiHealthService.startMonitoring();
      
      expect(apiHealthService.healthCheckTimer).toBe(initialTimer);
    });

    it('should stop monitoring and clear timer', () => {
      apiHealthService.startMonitoring();
      expect(apiHealthService.monitoringActive).toBe(true);
      
      apiHealthService.stopMonitoring();
      
      expect(apiHealthService.monitoringActive).toBe(false);
      expect(apiHealthService.healthCheckTimer).toBeNull();
    });

    it('should perform periodic health checks', async () => {
      apiHealthService.startMonitoring();
      
      // Clear the initial call count
      global.fetch.mockClear();
      
      // Fast forward to trigger health check intervals
      await vi.advanceTimersByTimeAsync(30000); // 1 interval
      
      expect(global.fetch).toHaveBeenCalledTimes(1);
      
      // Advance another interval
      await vi.advanceTimersByTimeAsync(30000); // 2nd interval
      
      expect(global.fetch).toHaveBeenCalledTimes(2);
    });
  });

  describe('Subscription Management', () => {
    it('should add subscribers and notify immediately', () => {
      const mockCallback = vi.fn();
      
      const unsubscribe = apiHealthService.subscribe(mockCallback);
      
      expect(apiHealthService.subscribers.size).toBe(1);
      expect(mockCallback).toHaveBeenCalledWith(
        expect.objectContaining({
          overall: 'unknown',
          endpoints: [],
          isMonitoring: false
        })
      );
      
      expect(typeof unsubscribe).toBe('function');
    });

    it('should remove subscribers when unsubscribe is called', () => {
      const mockCallback = vi.fn();
      
      const unsubscribe = apiHealthService.subscribe(mockCallback);
      expect(apiHealthService.subscribers.size).toBe(1);
      
      unsubscribe();
      expect(apiHealthService.subscribers.size).toBe(0);
    });

    it('should notify all subscribers of health changes', () => {
      const callback1 = vi.fn();
      const callback2 = vi.fn();
      
      apiHealthService.subscribe(callback1);
      apiHealthService.subscribe(callback2);
      
      vi.clearAllMocks();
      
      apiHealthService.notifySubscribers();
      
      expect(callback1).toHaveBeenCalled();
      expect(callback2).toHaveBeenCalled();
    });

    it('should handle subscriber callback errors gracefully', () => {
      const errorCallback = vi.fn(() => {
        throw new Error('Subscriber error');
      });
      const normalCallback = vi.fn();
      
      apiHealthService.subscribe(errorCallback);
      apiHealthService.subscribe(normalCallback);
      
      expect(() => {
        apiHealthService.notifySubscribers();
      }).not.toThrow();
      
      expect(normalCallback).toHaveBeenCalled();
    });
  });

  describe('Health Check Execution', () => {
    it('should check all defined endpoints', async () => {
      await apiHealthService.performHealthCheck();
      
      const expectedEndpoints = [
        '/health',
        '/api/health',
        '/emergency-health',
        '/api/settings/api-keys',
        '/stocks?limit=1'
      ];
      
      expect(global.fetch).toHaveBeenCalledTimes(5);
      
      expectedEndpoints.forEach((path, index) => {
        expect(global.fetch).toHaveBeenNthCalledWith(
          index + 1,
          expect.stringContaining(path),
          expect.objectContaining({
            method: 'GET',
            headers: expect.objectContaining({
              'Accept': 'application/json',
              'Cache-Control': 'no-cache'
            })
          })
        );
      });
    });

    it('should update health status after successful checks', async () => {
      await apiHealthService.performHealthCheck();
      
      const status = apiHealthService.getHealthStatus();
      
      expect(status.overall).toBe('healthy');
      expect(status.endpoints).toHaveLength(5);
      expect(status.lastCheck).toBeGreaterThan(0);
      
      status.endpoints.forEach(endpoint => {
        expect(endpoint.healthy).toBe(true);
        expect(endpoint.status).toBe(200);
        expect(endpoint.duration).toBeGreaterThan(0);
      });
    });

    it('should handle endpoint failures correctly', async () => {
      global.fetch.mockRejectedValue(new Error('Network error'));
      
      await apiHealthService.performHealthCheck();
      
      const status = apiHealthService.getHealthStatus();
      
      expect(status.overall).toBe('down');
      status.endpoints.forEach(endpoint => {
        expect(endpoint.healthy).toBe(false);
        expect(endpoint.error).toBe('Network error');
      });
    });

    it('should handle mixed endpoint results', async () => {
      global.fetch
        .mockResolvedValueOnce({ ok: true, status: 200, headers: { get: () => null } }) // health - success
        .mockResolvedValueOnce({ ok: true, status: 200, headers: { get: () => null } }) // api-health - success
        .mockRejectedValueOnce(new Error('Timeout')) // emergency-health - fail
        .mockResolvedValueOnce({ ok: false, status: 500, headers: { get: () => null } }) // settings - fail
        .mockResolvedValueOnce({ ok: true, status: 200, headers: { get: () => null } }); // stocks - success
      
      await apiHealthService.performHealthCheck();
      
      const status = apiHealthService.getHealthStatus();
      
      // Should be healthy because critical endpoints (health, api-health) are working
      expect(status.overall).toBe('healthy');
      
      const healthyEndpoints = status.endpoints.filter(e => e.healthy);
      expect(healthyEndpoints).toHaveLength(3);
    });

    it('should skip health check when circuit breaker is open', async () => {
      apiHealthService.healthStatus.circuitBreakerOpen = true;
      apiHealthService.healthStatus.lastCheck = Date.now();
      
      await apiHealthService.performHealthCheck();
      
      expect(global.fetch).not.toHaveBeenCalled();
    });

    it('should reset circuit breaker after timeout', async () => {
      apiHealthService.healthStatus.circuitBreakerOpen = true;
      apiHealthService.healthStatus.lastCheck = Date.now() - 70000; // 70 seconds ago
      
      await apiHealthService.performHealthCheck();
      
      expect(global.fetch).toHaveBeenCalled();
      expect(apiHealthService.healthStatus.circuitBreakerOpen).toBe(false);
      expect(apiHealthService.healthStatus.consecutiveFailures).toBe(0);
    });
  });

  describe('Individual Endpoint Checking', () => {
    it('should check endpoint with correct configuration', async () => {
      const endpoint = { name: 'test', path: '/test', critical: true };
      
      await apiHealthService.checkEndpoint(endpoint);
      
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/test'),
        expect.objectContaining({
          method: 'GET',
          headers: {
            'Accept': 'application/json',
            'Cache-Control': 'no-cache'
          },
          signal: expect.objectContaining({ timeout: 5000 })
        })
      );
    });

    it('should handle successful endpoint response', async () => {
      const endpoint = { name: 'test', path: '/test', critical: true };
      
      const result = await apiHealthService.checkEndpoint(endpoint);
      
      expect(result).toEqual(expect.objectContaining({
        name: 'test',
        path: '/test',
        healthy: true,
        status: 200,
        duration: expect.any(Number),
        critical: true,
        timestamp: expect.any(String)
      }));
    });

    it('should handle endpoint timeout', async () => {
      global.fetch.mockRejectedValue(new Error('AbortError'));
      
      const endpoint = { name: 'timeout', path: '/timeout', critical: false };
      
      const result = await apiHealthService.checkEndpoint(endpoint);
      
      expect(result).toEqual(expect.objectContaining({
        name: 'timeout',
        healthy: false,
        error: 'AbortError',
        critical: false
      }));
    });

    it('should parse JSON response data when available', async () => {
      const mockJsonData = { version: '1.0', status: 'ok' };
      
      global.fetch.mockResolvedValue({
        ok: true,
        status: 200,
        headers: {
          get: vi.fn(() => 'application/json')
        },
        json: vi.fn().mockResolvedValue(mockJsonData)
      });
      
      const endpoint = { name: 'json-test', path: '/json', critical: true };
      
      const result = await apiHealthService.checkEndpoint(endpoint);
      
      expect(result.data).toEqual(mockJsonData);
    });

    it('should handle JSON parse errors gracefully', async () => {
      global.fetch.mockResolvedValue({
        ok: true,
        status: 200,
        headers: {
          get: vi.fn(() => 'application/json')
        },
        json: vi.fn().mockRejectedValue(new Error('Invalid JSON'))
      });
      
      const endpoint = { name: 'bad-json', path: '/bad-json', critical: true };
      
      const result = await apiHealthService.checkEndpoint(endpoint);
      
      expect(result.healthy).toBe(true);
      expect(result.data).toBeUndefined();
    });
  });

  describe('Health Status Determination', () => {
    it('should return down when no critical endpoints are healthy', () => {
      const health = apiHealthService.determineOverallHealth(2, 5, 0, 2);
      expect(health).toBe('down');
    });

    it('should return healthy when all critical endpoints healthy and >80% total', () => {
      const health = apiHealthService.determineOverallHealth(4, 5, 2, 2);
      expect(health).toBe('healthy');
    });

    it('should return degraded when all critical healthy but 50-80% total', () => {
      const health = apiHealthService.determineOverallHealth(3, 5, 2, 2);
      expect(health).toBe('degraded');
    });

    it('should return unhealthy when all critical healthy but <50% total', () => {
      const health = apiHealthService.determineOverallHealth(2, 5, 2, 2);
      expect(health).toBe('unhealthy');
    });

    it('should return degraded when some critical endpoints are down', () => {
      const health = apiHealthService.determineOverallHealth(4, 5, 1, 2);
      expect(health).toBe('degraded');
    });
  });

  describe('Circuit Breaker Logic', () => {
    it('should open circuit breaker after consecutive failures', () => {
      // Simulate consecutive failures
      apiHealthService.handleCircuitBreaker('down');
      expect(apiHealthService.healthStatus.consecutiveFailures).toBe(1);
      expect(apiHealthService.healthStatus.circuitBreakerOpen).toBe(false);
      
      apiHealthService.handleCircuitBreaker('unhealthy');
      expect(apiHealthService.healthStatus.consecutiveFailures).toBe(2);
      expect(apiHealthService.healthStatus.circuitBreakerOpen).toBe(false);
      
      apiHealthService.handleCircuitBreaker('down');
      expect(apiHealthService.healthStatus.consecutiveFailures).toBe(3);
      expect(apiHealthService.healthStatus.circuitBreakerOpen).toBe(true);
    });

    it('should reset failure count on health recovery', () => {
      // Set up failure state
      apiHealthService.healthStatus.consecutiveFailures = 2;
      apiHealthService.healthStatus.circuitBreakerOpen = true;
      
      apiHealthService.handleCircuitBreaker('healthy');
      
      expect(apiHealthService.healthStatus.consecutiveFailures).toBe(0);
      expect(apiHealthService.healthStatus.circuitBreakerOpen).toBe(false);
    });

    it('should close circuit breaker on degraded health', () => {
      apiHealthService.healthStatus.circuitBreakerOpen = true;
      
      apiHealthService.handleCircuitBreaker('degraded');
      
      expect(apiHealthService.healthStatus.circuitBreakerOpen).toBe(false);
    });
  });

  describe('API Availability Checking', () => {
    it('should return true when circuit breaker closed and not down', () => {
      apiHealthService.healthStatus.circuitBreakerOpen = false;
      apiHealthService.healthStatus.overall = 'healthy';
      
      expect(apiHealthService.isApiAvailable()).toBe(true);
    });

    it('should return false when circuit breaker is open', () => {
      apiHealthService.healthStatus.circuitBreakerOpen = true;
      apiHealthService.healthStatus.overall = 'healthy';
      
      expect(apiHealthService.isApiAvailable()).toBe(false);
    });

    it('should return false when system is down', () => {
      apiHealthService.healthStatus.circuitBreakerOpen = false;
      apiHealthService.healthStatus.overall = 'down';
      
      expect(apiHealthService.isApiAvailable()).toBe(false);
    });
  });

  describe('Fallback Strategy Determination', () => {
    it('should return correct fallback strategies for each health status', () => {
      const strategies = {
        'healthy': 'none',
        'degraded': 'graceful_degradation', 
        'unhealthy': 'local_cache',
        'down': 'offline_mode',
        'unknown': 'unknown'
      };
      
      Object.entries(strategies).forEach(([status, expectedStrategy]) => {
        apiHealthService.healthStatus.overall = status;
        expect(apiHealthService.getFallbackStrategy()).toBe(expectedStrategy);
      });
    });
  });

  describe('Base URL Configuration', () => {
    it('should return localhost URL for development', () => {
      process.env.NODE_ENV = 'development';
      
      const baseUrl = apiHealthService.getBaseUrl();
      
      expect(baseUrl).toBe('http://localhost:3000');
    });

    it('should return production URL for non-development', () => {
      process.env.NODE_ENV = 'production';
      
      const baseUrl = apiHealthService.getBaseUrl();
      
      expect(baseUrl).toBe('https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev');
    });
  });

  describe('Force Health Check', () => {
    it('should perform immediate health check and return status', async () => {
      const status = await apiHealthService.forceHealthCheck();
      
      expect(global.fetch).toHaveBeenCalled();
      expect(status).toEqual(expect.objectContaining({
        overall: expect.any(String),
        endpoints: expect.any(Array),
        lastCheck: expect.any(Number)
      }));
    });
  });

  describe('Health Summary Generation', () => {
    it('should generate comprehensive health summary', async () => {
      await apiHealthService.performHealthCheck();
      
      const summary = apiHealthService.getHealthSummary();
      
      expect(summary).toEqual(expect.objectContaining({
        status: expect.any(String),
        healthy: expect.any(Number),
        total: expect.any(Number),
        percentage: expect.any(Number),
        circuitBreakerOpen: expect.any(Boolean),
        lastCheck: expect.any(Number),
        fallbackStrategy: expect.any(String)
      }));
      
      expect(summary.percentage).toBeGreaterThanOrEqual(0);
      expect(summary.percentage).toBeLessThanOrEqual(100);
    });

    it('should handle empty endpoints in summary', () => {
      const summary = apiHealthService.getHealthSummary();
      
      expect(summary.total).toBe(0);
      expect(summary.healthy).toBe(0);
      expect(summary.percentage).toBe(0);
    });

    it('should calculate correct health percentage', async () => {
      // Mock 3 healthy, 2 unhealthy endpoints
      global.fetch
        .mockResolvedValueOnce({ ok: true, status: 200, headers: { get: () => null } })
        .mockResolvedValueOnce({ ok: true, status: 200, headers: { get: () => null } })
        .mockRejectedValueOnce(new Error('Fail'))
        .mockRejectedValueOnce(new Error('Fail'))
        .mockResolvedValueOnce({ ok: true, status: 200, headers: { get: () => null } });
      
      await apiHealthService.performHealthCheck();
      
      const summary = apiHealthService.getHealthSummary();
      
      expect(summary.healthy).toBe(3);
      expect(summary.total).toBe(5);
      expect(summary.percentage).toBe(60);
    });
  });

  describe('Error Handling and Edge Cases', () => {
    it('should handle fetch network errors', async () => {
      global.fetch.mockRejectedValue(new Error('Network unreachable'));
      
      await apiHealthService.performHealthCheck();
      
      const status = apiHealthService.getHealthStatus();
      expect(status.overall).toBe('down');
    });

    it('should handle malformed endpoint configurations', async () => {
      const malformedEndpoint = { name: null, path: undefined, critical: 'invalid' };
      
      expect(async () => {
        await apiHealthService.checkEndpoint(malformedEndpoint);
      }).not.toThrow();
    });

    it('should handle very slow endpoint responses', async () => {
      global.fetch.mockImplementation(() => 
        new Promise(resolve => 
          setTimeout(() => resolve({ ok: true, status: 200, headers: { get: () => null } }), 10000)
        )
      );
      
      await apiHealthService.performHealthCheck();
      
      // Should timeout and mark endpoints as unhealthy
      const status = apiHealthService.getHealthStatus();
      expect(status.overall).toBe('down');
    });

    it('should handle concurrent health checks safely', async () => {
      const promises = Array.from({ length: 5 }, () => 
        apiHealthService.performHealthCheck()
      );
      
      await Promise.all(promises);
      
      // Should handle gracefully without race conditions
      const status = apiHealthService.getHealthStatus();
      expect(status.lastCheck).toBeGreaterThan(0);
    });

    it('should handle HTTP error status codes', async () => {
      global.fetch.mockResolvedValue({
        ok: false,
        status: 503,
        headers: { get: () => null }
      });
      
      await apiHealthService.performHealthCheck();
      
      const status = apiHealthService.getHealthStatus();
      expect(status.overall).toBe('down');
      
      status.endpoints.forEach(endpoint => {
        expect(endpoint.healthy).toBe(false);
        expect(endpoint.status).toBe(503);
      });
    });
  });

  describe('Monitoring Integration', () => {
    it('should notify subscribers when health changes', async () => {
      const callback = vi.fn();
      apiHealthService.subscribe(callback);
      
      vi.clearAllMocks();
      
      await apiHealthService.performHealthCheck();
      
      expect(callback).toHaveBeenCalledWith(
        expect.objectContaining({
          overall: 'healthy'
        })
      );
    });

    it('should handle multiple monitoring sessions', () => {
      apiHealthService.startMonitoring();
      apiHealthService.startMonitoring(); // Should not create multiple timers
      
      expect(apiHealthService.monitoringActive).toBe(true);
      
      apiHealthService.stopMonitoring();
      apiHealthService.stopMonitoring(); // Should handle gracefully
      
      expect(apiHealthService.monitoringActive).toBe(false);
    });
  });

  describe('Real-World Scenarios', () => {
    it('should handle gradual system degradation', async () => {
      // Start healthy
      await apiHealthService.performHealthCheck();
      expect(apiHealthService.getHealthStatus().overall).toBe('healthy');
      
      // Simulate one endpoint failing
      global.fetch
        .mockResolvedValueOnce({ ok: true, status: 200, headers: { get: () => null } })
        .mockResolvedValueOnce({ ok: true, status: 200, headers: { get: () => null } })
        .mockRejectedValueOnce(new Error('Fail'))
        .mockResolvedValueOnce({ ok: true, status: 200, headers: { get: () => null } })
        .mockResolvedValueOnce({ ok: true, status: 200, headers: { get: () => null } });
      
      await apiHealthService.performHealthCheck();
      expect(apiHealthService.getHealthStatus().overall).toBe('healthy'); // Still healthy
      
      // Simulate critical endpoint failing
      global.fetch
        .mockRejectedValueOnce(new Error('Critical fail'))
        .mockResolvedValueOnce({ ok: true, status: 200, headers: { get: () => null } })
        .mockResolvedValueOnce({ ok: true, status: 200, headers: { get: () => null } })
        .mockResolvedValueOnce({ ok: true, status: 200, headers: { get: () => null } })
        .mockResolvedValueOnce({ ok: true, status: 200, headers: { get: () => null } });
      
      await apiHealthService.performHealthCheck();
      expect(apiHealthService.getHealthStatus().overall).toBe('degraded');
    });

    it('should handle complete system recovery', async () => {
      // Start with circuit breaker open
      apiHealthService.healthStatus.circuitBreakerOpen = true;
      apiHealthService.healthStatus.consecutiveFailures = 3;
      apiHealthService.healthStatus.lastCheck = Date.now() - 70000;
      
      await apiHealthService.performHealthCheck();
      
      expect(apiHealthService.healthStatus.circuitBreakerOpen).toBe(false);
      expect(apiHealthService.healthStatus.consecutiveFailures).toBe(0);
      expect(apiHealthService.getHealthStatus().overall).toBe('healthy');
    });

    it('should provide appropriate fallback strategies during outages', () => {
      const scenarios = [
        { health: 'healthy', fallback: 'none' },
        { health: 'degraded', fallback: 'graceful_degradation' },
        { health: 'unhealthy', fallback: 'local_cache' },
        { health: 'down', fallback: 'offline_mode' }
      ];
      
      scenarios.forEach(({ health, fallback }) => {
        apiHealthService.healthStatus.overall = health;
        expect(apiHealthService.getFallbackStrategy()).toBe(fallback);
      });
    });
  });

  describe('Performance and Resource Management', () => {
    it('should handle high frequency health checks efficiently', async () => {
      const startTime = performance.now();
      
      for (let i = 0; i < 10; i++) {
        await apiHealthService.performHealthCheck();
      }
      
      const duration = performance.now() - startTime;
      expect(duration).toBeLessThan(1000); // Should complete within 1 second
    });

    it('should clean up resources on stop monitoring', () => {
      apiHealthService.startMonitoring();
      
      const setIntervalSpy = vi.spyOn(global, 'setInterval');
      const clearIntervalSpy = vi.spyOn(global, 'clearInterval');
      
      apiHealthService.stopMonitoring();
      
      expect(clearIntervalSpy).toHaveBeenCalled();
    });
  });
});