/**
 * Performance Testing Setup
 * Configuration and utilities for performance testing
 */

import { beforeAll, afterAll, beforeEach, afterEach } from 'vitest';

// Performance measurement utilities
global.performance = global.performance || {
  now: () => Date.now(),
  mark: () => {},
  measure: () => {},
  getEntriesByName: () => [],
  clearMarks: () => {},
  clearMeasures: () => {}
};

// Performance test utilities
global.performanceUtils = {
  // Measure function execution time
  measureTime: async (fn) => {
    const start = performance.now();
    const result = await fn();
    const end = performance.now();
    return {
      result,
      duration: end - start
    };
  },

  // Measure component render time
  measureRender: (renderFn) => {
    const start = performance.now();
    const result = renderFn();
    const end = performance.now();
    return {
      result,
      renderTime: end - start
    };
  },

  // Memory usage measurement (mock for testing)
  measureMemory: () => ({
    used: Math.random() * 100,
    total: 1000,
    percentage: Math.random() * 10
  }),

  // Network performance simulation
  simulateNetworkDelay: (ms = 100) => {
    return new Promise(resolve => setTimeout(resolve, ms));
  },

  // Load testing utilities
  simulateLoad: async (fn, concurrency = 10, iterations = 100) => {
    const promises = [];
    const results = [];

    for (let i = 0; i < concurrency; i++) {
      promises.push(
        (async () => {
          for (let j = 0; j < iterations / concurrency; j++) {
            const start = performance.now();
            try {
              await fn();
              const end = performance.now();
              results.push({
                success: true,
                duration: end - start,
                timestamp: Date.now()
              });
            } catch (error) {
              results.push({
                success: false,
                error: error.message,
                timestamp: Date.now()
              });
            }
          }
        })()
      );
    }

    await Promise.all(promises);
    return results;
  }
};

// Mock heavy operations for performance testing
global.mockHeavyOperations = {
  // Simulate expensive calculations
  heavyCalculation: (complexity = 1000) => {
    let result = 0;
    for (let i = 0; i < complexity * 1000; i++) {
      result += Math.sqrt(i);
    }
    return result;
  },

  // Simulate data processing
  processLargeDataset: (size = 10000) => {
    const data = Array.from({ length: size }, (_, i) => ({
      id: i,
      value: Math.random() * 100,
      timestamp: Date.now() + i
    }));

    return data
      .filter(item => item.value > 50)
      .map(item => ({ ...item, processed: true }))
      .sort((a, b) => b.value - a.value);
  }
};

beforeAll(() => {
  console.log('🚀 Performance testing setup initialized');
});

beforeEach(() => {
  // Clear performance marks before each test
  if (performance.clearMarks) {
    performance.clearMarks();
  }
  if (performance.clearMeasures) {
    performance.clearMeasures();
  }
});

afterEach(() => {
  // Clean up after each performance test
  if (global.gc) {
    global.gc(); // Force garbage collection if available
  }
});

afterAll(() => {
  console.log('🏁 Performance testing cleanup completed');
});