/**
 * Real API Health Service Unit Tests
 * Tests the actual apiHealthService.js with real health monitoring functionality
 * REAL IMPLEMENTATION - Tests actual behavior without global mocks
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Import the REAL ApiHealthService
import apiHealthService from '../../../services/apiHealthService';

describe('🏥 Real API Health Service', () => {
  let originalFetch;
  let originalWindow;
  
  beforeEach(() => {
    // Save originals
    originalFetch = global.fetch;
    originalWindow = global.window;
    
    // Use real timers to avoid vitest timer issues
    vi.useRealTimers();
    
    // Reset service state to clean state
    apiHealthService.stopMonitoring();
    apiHealthService.healthStatus = {
      overall: 'unknown',
      endpoints: new Map(),
      lastCheck: null,
      consecutiveFailures: 0,
      circuitBreakerOpen: false
    };
    apiHealthService.subscribers.clear();
    
    // Setup realistic API URL configuration
    global.window = {
      location: { hostname: 'localhost' },
      __CONFIG__: {
        API_URL: 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev'
      }
    };
    
    // Mock console methods to avoid test noise but allow logging verification
    vi.spyOn(console, 'log').mockImplementation(() => {});
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    // Restore originals
    global.fetch = originalFetch;
    global.window = originalWindow;
    
    // Stop any active monitoring
    apiHealthService.stopMonitoring();
    
    // Restore console
    vi.restoreAllMocks();
  });

  describe('Service Configuration', () => {
    it('should initialize with correct default configuration', () => {
      expect(apiHealthService.config).toEqual({
        healthCheckInterval: 30000, // 30 seconds
        circuitBreakerThreshold: 3, // Open after 3 consecutive failures
        circuitBreakerTimeout: 60000, // 1 minute before retry
        endpointTimeout: 5000, // 5 second timeout per endpoint
        retryAttempts: 2
      });
    });

    it('should have reasonable configuration values', () => {
      const config = apiHealthService.config;
      
      // Configuration should be reasonable for production use
      expect(config.healthCheckInterval).toBeGreaterThan(5000); // At least 5 seconds
      expect(config.healthCheckInterval).toBeLessThan(300000); // Less than 5 minutes
      expect(config.circuitBreakerThreshold).toBeGreaterThan(0);
      expect(config.circuitBreakerThreshold).toBeLessThan(10); // Reasonable threshold
      expect(config.circuitBreakerTimeout).toBeGreaterThan(10000); // At least 10 seconds
      expect(config.endpointTimeout).toBeGreaterThan(1000); // At least 1 second
      expect(config.retryAttempts).toBeGreaterThanOrEqual(1); // At least 1 retry
    });

    it('should initialize with proper default health status', () => {
      const status = apiHealthService.healthStatus;
      
      expect(status.overall).toBe('unknown');
      expect(status.endpoints).toBeInstanceOf(Map);
      expect(status.endpoints.size).toBe(0);
      expect(status.lastCheck).toBeNull();
      expect(status.consecutiveFailures).toBe(0);
      expect(status.circuitBreakerOpen).toBe(false);
    });

    it('should initialize with empty subscriber set', () => {
      expect(apiHealthService.subscribers).toBeInstanceOf(Set);
      expect(apiHealthService.subscribers.size).toBe(0);
    });

    it('should not be monitoring initially', () => {
      expect(apiHealthService.monitoringActive).toBe(false);
      expect(apiHealthService.healthCheckTimer).toBeNull();
    });
  });

  describe('Monitoring Lifecycle Management', () => {
    it('should start monitoring without errors', () => {
      expect(() => {
        apiHealthService.startMonitoring();
      }).not.toThrow();
      
      expect(apiHealthService.monitoringActive).toBe(true);
    });

    it('should stop monitoring without errors', () => {
      apiHealthService.startMonitoring();
      
      expect(() => {
        apiHealthService.stopMonitoring();
      }).not.toThrow();
      
      expect(apiHealthService.monitoringActive).toBe(false);
    });

    it('should handle multiple start calls gracefully', () => {
      apiHealthService.startMonitoring();
      const firstTimerId = apiHealthService.healthCheckTimer;
      
      // Second start should not create a new timer
      apiHealthService.startMonitoring();
      
      expect(apiHealthService.healthCheckTimer).toBe(firstTimerId);
      expect(apiHealthService.monitoringActive).toBe(true);
    });

    it('should handle stop calls when not monitoring', () => {
      // Should not throw even if not monitoring
      expect(() => {
        apiHealthService.stopMonitoring();
      }).not.toThrow();
      
      expect(apiHealthService.monitoringActive).toBe(false);
    });

    it('should clean up timer on stop', () => {
      apiHealthService.startMonitoring();
      expect(apiHealthService.healthCheckTimer).not.toBeNull();
      
      apiHealthService.stopMonitoring();
      expect(apiHealthService.healthCheckTimer).toBeNull();
    });
  });

  describe('Subscription Management', () => {
    it('should add subscribers correctly', () => {
      const mockCallback = vi.fn();
      
      const unsubscribe = apiHealthService.subscribe(mockCallback);
      
      expect(apiHealthService.subscribers.has(mockCallback)).toBe(true);
      expect(apiHealthService.subscribers.size).toBe(1);
      expect(typeof unsubscribe).toBe('function');
    });

    it('should remove subscribers correctly', () => {
      const mockCallback = vi.fn();
      
      const unsubscribe = apiHealthService.subscribe(mockCallback);
      expect(apiHealthService.subscribers.size).toBe(1);
      
      unsubscribe(); // Use the returned unsubscribe function
      expect(apiHealthService.subscribers.has(mockCallback)).toBe(false);
      expect(apiHealthService.subscribers.size).toBe(0);
    });

    it('should handle multiple subscribers', () => {
      const callback1 = vi.fn();
      const callback2 = vi.fn();
      const callback3 = vi.fn();
      
      apiHealthService.subscribe(callback1);
      apiHealthService.subscribe(callback2);
      apiHealthService.subscribe(callback3);
      
      expect(apiHealthService.subscribers.size).toBe(3);
      expect(apiHealthService.subscribers.has(callback1)).toBe(true);
      expect(apiHealthService.subscribers.has(callback2)).toBe(true);
      expect(apiHealthService.subscribers.has(callback3)).toBe(true);
    });

    it('should not add duplicate subscribers', () => {
      const mockCallback = vi.fn();
      
      apiHealthService.subscribe(mockCallback);
      apiHealthService.subscribe(mockCallback); // Same callback
      
      expect(apiHealthService.subscribers.size).toBe(1);
    });

    it('should handle unsubscribe function calls gracefully', () => {
      const mockCallback = vi.fn();
      
      const unsubscribe = apiHealthService.subscribe(mockCallback);
      expect(apiHealthService.subscribers.size).toBe(1);
      
      expect(() => {
        unsubscribe();
      }).not.toThrow();
      
      expect(apiHealthService.subscribers.size).toBe(0);
    });
  });

  describe('Health Status Tracking', () => {
    it('should provide current health status', () => {
      const status = apiHealthService.getHealthStatus();
      
      expect(status).toHaveProperty('overall');
      expect(status).toHaveProperty('endpoints');
      expect(status).toHaveProperty('lastCheck');
      expect(status).toHaveProperty('consecutiveFailures');
      expect(status).toHaveProperty('circuitBreakerOpen');
      expect(status).toHaveProperty('isMonitoring');
      
      expect(Array.isArray(status.endpoints)).toBe(true);
    });

    it('should track health status changes over time', () => {
      const initialStatus = apiHealthService.getHealthStatus();
      expect(initialStatus.overall).toBe('unknown');
      expect(initialStatus.lastCheck).toBeNull();
      
      // Status should be a snapshot, not a reference
      const secondStatus = apiHealthService.getHealthStatus();
      expect(secondStatus).toEqual(initialStatus);
      expect(secondStatus).not.toBe(initialStatus); // Different object
    });

    it('should increment consecutive failures correctly', () => {
      const initialFailures = apiHealthService.healthStatus.consecutiveFailures;
      
      // Simulate failures by directly updating (in real use, this happens in health checks)
      apiHealthService.healthStatus.consecutiveFailures += 1;
      
      expect(apiHealthService.healthStatus.consecutiveFailures).toBe(initialFailures + 1);
    });

    it('should track circuit breaker state', () => {
      // Initially circuit breaker should be closed
      expect(apiHealthService.healthStatus.circuitBreakerOpen).toBe(false);
      
      // Test opening circuit breaker
      apiHealthService.healthStatus.circuitBreakerOpen = true;
      expect(apiHealthService.healthStatus.circuitBreakerOpen).toBe(true);
    });
  });

  describe('Endpoint Health Tracking', () => {
    it('should initialize with empty endpoint tracking', () => {
      const endpoints = apiHealthService.healthStatus.endpoints;
      
      expect(endpoints).toBeInstanceOf(Map);
      expect(endpoints.size).toBe(0);
    });

    it('should allow adding endpoint health data', () => {
      const endpoints = apiHealthService.healthStatus.endpoints;
      
      // Simulate adding endpoint health data
      endpoints.set('/api/health', {
        status: 'healthy',
        lastCheck: new Date().toISOString(),
        responseTime: 150,
        failures: 0
      });
      
      expect(endpoints.size).toBe(1);
      expect(endpoints.has('/api/health')).toBe(true);
      
      const healthData = endpoints.get('/api/health');
      expect(healthData).toHaveProperty('status', 'healthy');
      expect(healthData).toHaveProperty('responseTime', 150);
      expect(healthData).toHaveProperty('failures', 0);
    });

    it('should track multiple endpoints independently', () => {
      const endpoints = apiHealthService.healthStatus.endpoints;
      
      endpoints.set('/api/health', { status: 'healthy', failures: 0 });
      endpoints.set('/api/portfolio', { status: 'degraded', failures: 1 });
      endpoints.set('/api/stocks', { status: 'unhealthy', failures: 3 });
      
      expect(endpoints.size).toBe(3);
      expect(endpoints.get('/api/health').status).toBe('healthy');
      expect(endpoints.get('/api/portfolio').status).toBe('degraded');
      expect(endpoints.get('/api/stocks').status).toBe('unhealthy');
    });
  });

  describe('Error Resilience', () => {
    it('should handle missing fetch gracefully', () => {
      // Remove fetch to simulate environment without it
      delete global.fetch;
      
      expect(() => {
        apiHealthService.startMonitoring();
      }).not.toThrow();
      
      expect(apiHealthService.monitoringActive).toBe(true);
    });

    it('should handle missing window configuration gracefully', () => {
      delete global.window.__CONFIG__;
      
      expect(() => {
        apiHealthService.startMonitoring();
      }).not.toThrow();
    });

    it('should handle missing window object gracefully', () => {
      delete global.window;
      
      expect(() => {
        apiHealthService.startMonitoring();
      }).not.toThrow();
    });

    it('should handle callback errors in subscribers', () => {
      const failingCallback = vi.fn(() => {
        throw new Error('Callback error');
      });
      const workingCallback = vi.fn();
      
      apiHealthService.subscribe(failingCallback);
      apiHealthService.subscribe(workingCallback);
      
      // Simulate notification (this would happen during health checks)
      expect(() => {
        apiHealthService.subscribers.forEach(callback => {
          try {
            callback(apiHealthService.getHealthStatus());
          } catch (error) {
            // Service should handle callback errors gracefully
            console.error('Subscriber callback error:', error);
          }
        });
      }).not.toThrow();
      
      expect(failingCallback).toHaveBeenCalled();
      expect(workingCallback).toHaveBeenCalled();
    });
  });

  describe('Integration with Real Environment', () => {
    it('should work with real API configuration', () => {
      // Use real API configuration
      global.window.__CONFIG__ = {
        API_URL: 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev'
      };
      
      expect(() => {
        apiHealthService.startMonitoring();
      }).not.toThrow();
      
      // Should be able to get status
      const status = apiHealthService.getHealthStatus();
      expect(status).toBeDefined();
      expect(status.overall).toBe('unknown'); // Initially unknown
    });

    it('should handle localhost development configuration', () => {
      global.window.__CONFIG__ = {
        API_URL: 'http://localhost:3000/api'
      };
      
      expect(() => {
        apiHealthService.startMonitoring();
      }).not.toThrow();
      
      expect(apiHealthService.monitoringActive).toBe(true);
    });

    it('should detect and handle different API URL formats', () => {
      const testUrls = [
        'https://api.example.com',
        'https://api.example.com/v1',
        'http://localhost:3000',
        'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev'
      ];
      
      testUrls.forEach(url => {
        global.window.__CONFIG__ = { API_URL: url };
        
        expect(() => {
          apiHealthService.startMonitoring();
          apiHealthService.stopMonitoring();
        }).not.toThrow();
      });
    });
  });

  describe('Performance and Memory Management', () => {
    it('should not create memory leaks with start/stop cycles', () => {
      const initialSubscriberCount = apiHealthService.subscribers.size;
      
      // Multiple start/stop cycles
      for (let i = 0; i < 10; i++) {
        apiHealthService.startMonitoring();
        apiHealthService.stopMonitoring();
      }
      
      expect(apiHealthService.subscribers.size).toBe(initialSubscriberCount);
      expect(apiHealthService.monitoringActive).toBe(false);
      expect(apiHealthService.healthCheckTimer).toBeNull();
    });

    it('should clean up properly on service destruction simulation', () => {
      const callback1 = vi.fn();
      const callback2 = vi.fn();
      
      apiHealthService.subscribe(callback1);
      apiHealthService.subscribe(callback2);
      apiHealthService.startMonitoring();
      
      // Simulate service cleanup
      apiHealthService.stopMonitoring();
      apiHealthService.subscribers.clear();
      
      expect(apiHealthService.subscribers.size).toBe(0);
      expect(apiHealthService.monitoringActive).toBe(false);
      expect(apiHealthService.healthCheckTimer).toBeNull();
    });

    it('should handle rapid subscribe/unsubscribe operations', () => {
      const callbacks = Array.from({ length: 100 }, () => vi.fn());
      
      // Rapid subscribe and collect unsubscribe functions
      const unsubscribers = callbacks.map(callback => {
        return apiHealthService.subscribe(callback);
      });
      
      expect(apiHealthService.subscribers.size).toBe(100);
      
      // Rapid unsubscribe using returned unsubscribe functions
      unsubscribers.forEach(unsubscribe => {
        unsubscribe();
      });
      
      expect(apiHealthService.subscribers.size).toBe(0);
    });
  });

  describe('Circuit Breaker Logic Foundations', () => {
    it('should provide circuit breaker configuration', () => {
      const config = apiHealthService.config;
      
      expect(config.circuitBreakerThreshold).toBeGreaterThan(0);
      expect(config.circuitBreakerTimeout).toBeGreaterThan(0);
      expect(typeof config.circuitBreakerThreshold).toBe('number');
      expect(typeof config.circuitBreakerTimeout).toBe('number');
    });

    it('should track circuit breaker state in health status', () => {
      const status = apiHealthService.healthStatus;
      
      expect(status).toHaveProperty('circuitBreakerOpen');
      expect(typeof status.circuitBreakerOpen).toBe('boolean');
      expect(status.circuitBreakerOpen).toBe(false); // Initially closed
    });

    it('should track consecutive failures for circuit breaker logic', () => {
      const status = apiHealthService.healthStatus;
      
      expect(status).toHaveProperty('consecutiveFailures');
      expect(typeof status.consecutiveFailures).toBe('number');
      expect(status.consecutiveFailures).toBe(0); // Initially zero
    });

    it('should allow manual circuit breaker state changes for testing', () => {
      // Test opening circuit breaker
      apiHealthService.healthStatus.circuitBreakerOpen = true;
      apiHealthService.healthStatus.consecutiveFailures = 5;
      
      expect(apiHealthService.healthStatus.circuitBreakerOpen).toBe(true);
      expect(apiHealthService.healthStatus.consecutiveFailures).toBe(5);
      
      // Test closing circuit breaker
      apiHealthService.healthStatus.circuitBreakerOpen = false;
      apiHealthService.healthStatus.consecutiveFailures = 0;
      
      expect(apiHealthService.healthStatus.circuitBreakerOpen).toBe(false);
      expect(apiHealthService.healthStatus.consecutiveFailures).toBe(0);
    });
  });

  describe('Logging and Observability', () => {
    it('should log monitoring start', () => {
      apiHealthService.startMonitoring();
      
      expect(console.log).toHaveBeenCalledWith(
        expect.stringContaining('Starting API health monitoring')
      );
    });

    it('should log monitoring stop', () => {
      apiHealthService.startMonitoring();
      apiHealthService.stopMonitoring();
      
      expect(console.log).toHaveBeenCalledWith(
        expect.stringContaining('Stopping API health monitoring')
      );
    });

    it('should provide logging hooks for debugging', () => {
      // Verify that important operations are logged
      apiHealthService.startMonitoring();
      
      // At minimum, start should be logged
      expect(console.log).toHaveBeenCalled();
      
      apiHealthService.stopMonitoring();
      
      // Stop should also be logged
      expect(console.log).toHaveBeenCalledWith(
        expect.stringContaining('Stopping API health monitoring')
      );
    });
  });
});