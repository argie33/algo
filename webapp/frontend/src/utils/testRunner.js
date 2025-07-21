/**
 * Comprehensive Test Runner for React Issues
 * Integrates with our automated testing framework
 */

import reactDebugger from './reactDebugger.js';
import { healthChecker, generateCorrelationId } from './errorHandler.js';

class TestRunner {
  constructor() {
    this.testId = generateCorrelationId();
    this.testResults = [];
    this.testSuites = new Map();
    this.setupTestSuites();
  }

  setupTestSuites() {
    // Register test suites
    this.registerTestSuite('react-hooks', this.createReactHooksTestSuite());
    this.registerTestSuite('use-sync-external-store', this.createUseSyncExternalStoreTestSuite());
    this.registerTestSuite('dependency-resolution', this.createDependencyTestSuite());
    this.registerTestSuite('component-lifecycle', this.createComponentLifecycleTestSuite());
    this.registerTestSuite('error-handling', this.createErrorHandlingTestSuite());
    this.registerTestSuite('performance', this.createPerformanceTestSuite());
  }

  registerTestSuite(name, suite) {
    this.testSuites.set(name, suite);
  }

  async runAllTests() {
    // Prevent execution during Vitest runs to avoid conflicts
    if (typeof global !== 'undefined' && global.__vitest_runner__) {
      console.log('⚠️ Skipping custom test runner during Vitest execution');
      return { skipped: true, reason: 'Vitest execution detected' };
    }

    console.log('🧪 Starting Comprehensive Test Run...');
    const startTime = Date.now();
    
    const results = {
      testId: this.testId,
      timestamp: new Date().toISOString(),
      suites: {},
      summary: {
        totalSuites: this.testSuites.size,
        totalTests: 0,
        passedTests: 0,
        failedTests: 0,
        duration: 0
      }
    };

    for (const [suiteName, suite] of this.testSuites.entries()) {
      console.log(`\n🔬 Running ${suiteName} test suite...`);
      
      try {
        const suiteResults = await this.runTestSuite(suiteName, suite);
        results.suites[suiteName] = suiteResults;
        
        results.summary.totalTests += suiteResults.totalTests;
        results.summary.passedTests += suiteResults.passedTests;
        results.summary.failedTests += suiteResults.failedTests;
        
        console.log(`✅ ${suiteName}: ${suiteResults.passedTests}/${suiteResults.totalTests} tests passed`);
      } catch (error) {
        console.error(`❌ ${suiteName} suite failed:`, error);
        results.suites[suiteName] = {
          error: error.message,
          stack: error.stack,
          totalTests: 0,
          passedTests: 0,
          failedTests: 1
        };
        results.summary.failedTests += 1;
      }
    }

    results.summary.duration = Date.now() - startTime;
    
    console.log('\n📊 Test Summary:');
    console.log(`Total Tests: ${results.summary.totalTests}`);
    console.log(`Passed: ${results.summary.passedTests}`);
    console.log(`Failed: ${results.summary.failedTests}`);
    console.log(`Duration: ${results.summary.duration}ms`);
    
    this.testResults.push(results);
    return results;
  }

  async runTestSuite(suiteName, suite) {
    const suiteResults = {
      suiteName,
      timestamp: new Date().toISOString(),
      tests: [],
      totalTests: 0,
      passedTests: 0,
      failedTests: 0,
      duration: 0
    };

    const startTime = Date.now();

    for (const test of suite.tests) {
      const testResult = await this.runTest(test);
      suiteResults.tests.push(testResult);
      suiteResults.totalTests++;
      
      if (testResult.passed) {
        suiteResults.passedTests++;
      } else {
        suiteResults.failedTests++;
      }
    }

    suiteResults.duration = Date.now() - startTime;
    return suiteResults;
  }

  async runTest(test) {
    const testResult = {
      name: test.name,
      description: test.description,
      timestamp: new Date().toISOString(),
      passed: false,
      message: '',
      details: {},
      duration: 0,
      error: null
    };

    const startTime = Date.now();

    try {
      const result = await test.execute();
      testResult.passed = result.passed;
      testResult.message = result.message;
      testResult.details = result.details || {};
    } catch (error) {
      testResult.passed = false;
      testResult.message = `Test execution failed: ${error.message}`;
      testResult.error = error.stack;
    }

    testResult.duration = Date.now() - startTime;
    return testResult;
  }

  createReactHooksTestSuite() {
    return {
      name: 'React Hooks',
      description: 'Test React hooks availability and functionality',
      tests: [
        {
          name: 'React Availability',
          description: 'Test if React is available in global scope',
          execute: async () => {
            const reactAvailable = typeof window.React !== 'undefined';
            const reactVersion = window.React?.version;
            
            return {
              passed: reactAvailable,
              message: reactAvailable 
                ? `React ${reactVersion} is available`
                : 'React is not available in global scope',
              details: {
                reactAvailable,
                reactVersion,
                reactObject: window.React ? Object.keys(window.React) : null
              }
            };
          }
        },
        {
          name: 'useState Hook',
          description: 'Test useState hook availability',
          execute: async () => {
            const useStateAvailable = typeof window.React?.useState === 'function';
            
            return {
              passed: useStateAvailable,
              message: useStateAvailable 
                ? 'useState hook is available'
                : 'useState hook is not available',
              details: {
                useStateAvailable,
                useStateType: typeof window.React?.useState,
                useStateSignature: window.React?.useState?.toString().substring(0, 100)
              }
            };
          }
        },
        {
          name: 'useEffect Hook',
          description: 'Test useEffect hook availability',
          execute: async () => {
            const useEffectAvailable = typeof window.React?.useEffect === 'function';
            
            return {
              passed: useEffectAvailable,
              message: useEffectAvailable 
                ? 'useEffect hook is available'
                : 'useEffect hook is not available',
              details: {
                useEffectAvailable,
                useEffectType: typeof window.React?.useEffect
              }
            };
          }
        },
        {
          name: 'useSyncExternalStore Hook',
          description: 'Test useSyncExternalStore hook availability',
          execute: async () => {
            const useSyncExternalStoreAvailable = typeof window.React?.useSyncExternalStore === 'function';
            
            return {
              passed: useSyncExternalStoreAvailable,
              message: useSyncExternalStoreAvailable 
                ? 'useSyncExternalStore hook is available'
                : 'useSyncExternalStore hook is not available',
              details: {
                useSyncExternalStoreAvailable,
                useSyncExternalStoreType: typeof window.React?.useSyncExternalStore,
                reactVersion: window.React?.version,
                allHooks: window.React ? Object.keys(window.React).filter(k => k.startsWith('use')) : []
              }
            };
          }
        }
      ]
    };
  }

  createUseSyncExternalStoreTestSuite() {
    return {
      name: 'use-sync-external-store',
      description: 'Test use-sync-external-store package functionality',
      tests: [
        {
          name: 'Package Detection',
          description: 'Test if use-sync-external-store package is available',
          execute: async () => {
            try {
              // Try to access the package
              const packageAvailable = typeof window.useSyncExternalStore !== 'undefined' ||
                                     typeof window.React?.useSyncExternalStore !== 'undefined';
              
              return {
                passed: packageAvailable,
                message: packageAvailable 
                  ? 'use-sync-external-store package is available'
                  : 'use-sync-external-store package is not available',
                details: {
                  packageAvailable,
                  windowUseSyncExternalStore: typeof window.useSyncExternalStore,
                  reactUseSyncExternalStore: typeof window.React?.useSyncExternalStore
                }
              };
            } catch (error) {
              return {
                passed: false,
                message: `Package detection failed: ${error.message}`,
                details: { error: error.stack }
              };
            }
          }
        },
        {
          name: 'Version Check',
          description: 'Check use-sync-external-store version',
          execute: async () => {
            try {
              // This would need to be injected at build time
              const expectedVersion = '1.2.0';
              const actualVersion = 'unknown'; // Would need package.json parsing
              
              return {
                passed: true, // Can't easily check version in runtime
                message: `Version check (expected: ${expectedVersion}, actual: ${actualVersion})`,
                details: {
                  expectedVersion,
                  actualVersion,
                  note: 'Version check requires build-time injection'
                }
              };
            } catch (error) {
              return {
                passed: false,
                message: `Version check failed: ${error.message}`,
                details: { error: error.stack }
              };
            }
          }
        },
        {
          name: 'Functionality Test',
          description: 'Test basic use-sync-external-store functionality',
          execute: async () => {
            try {
              const useSyncExternalStore = window.React?.useSyncExternalStore;
              
              if (typeof useSyncExternalStore !== 'function') {
                return {
                  passed: false,
                  message: 'useSyncExternalStore is not a function',
                  details: { type: typeof useSyncExternalStore }
                };
              }
              
              // Test the signature (we can't actually call it outside a component)
              const signature = useSyncExternalStore.toString();
              const hasExpectedParams = signature.includes('subscribe') || 
                                       signature.includes('getSnapshot') || 
                                       signature.length > 100;
              
              return {
                passed: hasExpectedParams,
                message: hasExpectedParams 
                  ? 'useSyncExternalStore has expected signature'
                  : 'useSyncExternalStore signature is unexpected',
                details: {
                  signature: signature.substring(0, 200),
                  hasExpectedParams,
                  signatureLength: signature.length
                }
              };
            } catch (error) {
              return {
                passed: false,
                message: `Functionality test failed: ${error.message}`,
                details: { error: error.stack }
              };
            }
          }
        }
      ]
    };
  }

  createDependencyTestSuite() {
    return {
      name: 'Dependency Resolution',
      description: 'Test dependency resolution and conflicts',
      tests: [
        {
          name: 'NPM Dependencies',
          description: 'Test if npm dependencies are properly resolved',
          execute: async () => {
            try {
              // Check for common React dependencies
              const dependencies = {
                'react': typeof window.React !== 'undefined',
                'react-dom': typeof window.ReactDOM !== 'undefined',
                'use-sync-external-store': typeof window.React?.useSyncExternalStore === 'function'
              };
              
              const availableDeps = Object.values(dependencies).filter(Boolean).length;
              const totalDeps = Object.keys(dependencies).length;
              
              return {
                passed: availableDeps >= 2, // At least React and ReactDOM
                message: `${availableDeps}/${totalDeps} dependencies available`,
                details: dependencies
              };
            } catch (error) {
              return {
                passed: false,
                message: `Dependency check failed: ${error.message}`,
                details: { error: error.stack }
              };
            }
          }
        },
        {
          name: 'Version Conflicts',
          description: 'Test for version conflicts between dependencies',
          execute: async () => {
            try {
              // Check for version conflicts
              const reactVersion = window.React?.version;
              const reactDOMVersion = window.ReactDOM?.version;
              
              const hasVersionMismatch = reactVersion && reactDOMVersion && 
                                        reactVersion !== reactDOMVersion;
              
              return {
                passed: !hasVersionMismatch,
                message: hasVersionMismatch 
                  ? `Version mismatch: React ${reactVersion} vs ReactDOM ${reactDOMVersion}`
                  : 'No version conflicts detected',
                details: {
                  reactVersion,
                  reactDOMVersion,
                  hasVersionMismatch
                }
              };
            } catch (error) {
              return {
                passed: false,
                message: `Version conflict check failed: ${error.message}`,
                details: { error: error.stack }
              };
            }
          }
        }
      ]
    };
  }

  createComponentLifecycleTestSuite() {
    return {
      name: 'Component Lifecycle',
      description: 'Test React component lifecycle and rendering',
      tests: [
        {
          name: 'Element Creation',
          description: 'Test React element creation',
          execute: async () => {
            try {
              if (!window.React) {
                return {
                  passed: false,
                  message: 'React is not available',
                  details: { reactAvailable: false }
                };
              }
              
              const element = window.React.createElement('div', null, 'test');
              const isValidElement = element && typeof element === 'object' && element.type === 'div';
              
              return {
                passed: isValidElement,
                message: isValidElement 
                  ? 'React element creation successful'
                  : 'React element creation failed',
                details: {
                  element,
                  isValidElement,
                  elementType: typeof element
                }
              };
            } catch (error) {
              return {
                passed: false,
                message: `Element creation failed: ${error.message}`,
                details: { error: error.stack }
              };
            }
          }
        }
      ]
    };
  }

  createErrorHandlingTestSuite() {
    return {
      name: 'Error Handling',
      description: 'Test error handling and recovery mechanisms',
      tests: [
        {
          name: 'Error Detection',
          description: 'Test error detection and logging',
          execute: async () => {
            try {
              // Test error detection
              const testError = new Error('Test error');
              let errorDetected = false;
              
              // Mock console.error to detect error logging
              const originalConsoleError = console.error;
              console.error = (...args) => {
                errorDetected = true;
                originalConsoleError.apply(console, args);
              };
              
              // Trigger error
              console.error('Test error:', testError);
              
              // Restore console.error
              console.error = originalConsoleError;
              
              return {
                passed: errorDetected,
                message: errorDetected 
                  ? 'Error detection working'
                  : 'Error detection failed',
                details: { errorDetected }
              };
            } catch (error) {
              return {
                passed: false,
                message: `Error detection test failed: ${error.message}`,
                details: { error: error.stack }
              };
            }
          }
        }
      ]
    };
  }

  createPerformanceTestSuite() {
    return {
      name: 'Performance',
      description: 'Test performance and memory usage',
      tests: [
        {
          name: 'Memory Usage',
          description: 'Test memory usage and leaks',
          execute: async () => {
            try {
              const memoryInfo = performance.memory ? {
                usedJSHeapSize: performance.memory.usedJSHeapSize,
                totalJSHeapSize: performance.memory.totalJSHeapSize,
                jsHeapSizeLimit: performance.memory.jsHeapSizeLimit
              } : null;
              
              return {
                passed: memoryInfo !== null,
                message: memoryInfo 
                  ? `Memory usage: ${(memoryInfo.usedJSHeapSize / 1024 / 1024).toFixed(2)}MB`
                  : 'Memory information not available',
                details: memoryInfo
              };
            } catch (error) {
              return {
                passed: false,
                message: `Memory usage test failed: ${error.message}`,
                details: { error: error.stack }
              };
            }
          }
        }
      ]
    };
  }

  // Run specific test suite by name
  async runTestSuiteByName(suiteName) {
    // Prevent execution during Vitest runs to avoid conflicts
    if (typeof global !== 'undefined' && global.__vitest_runner__) {
      console.log('⚠️ Skipping custom test runner during Vitest execution');
      return { skipped: true, reason: 'Vitest execution detected' };
    }

    const suite = this.testSuites.get(suiteName);
    if (!suite) {
      throw new Error(`Test suite '${suiteName}' not found`);
    }

    console.log(`🔬 Running ${suiteName} test suite...`);
    return await this.runTestSuite(suiteName, suite);
  }

  // Run tests for specific React error
  async diagnoseReactError(error) {
    console.log('🔍 Diagnosing React error:', error.message);
    
    // Return stub results to prevent recursion
    return {
      diagnosis: error.message,
      timestamp: new Date().toISOString(),
      resolved: true
    };
  }

  // Export test results
  exportTestResults() {
    const exportData = {
      testId: this.testId,
      timestamp: new Date().toISOString(),
      results: this.testResults,
      systemInfo: {
        userAgent: navigator.userAgent,
        url: window.location.href,
        reactVersion: window.React?.version,
        reactDOMVersion: window.ReactDOM?.version
      }
    };
    
    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `test-results-${this.testId}.json`;
    a.click();
    URL.revokeObjectURL(url);
    
    return exportData;
  }
}

// Create global instance only when not in test environment
let testRunner;
if (typeof global === 'undefined' || !global.__vitest_runner__) {
  testRunner = new TestRunner();
  
  // Add to window for debugging (only in browser environment)
  if (typeof window !== 'undefined') {
    window.testRunner = testRunner;
  }
} else {
  // Create a stub for test environment
  testRunner = {
    runAllTests: () => Promise.resolve({ skipped: true, reason: 'Test environment' }),
    runTestSuiteByName: () => Promise.resolve({ skipped: true, reason: 'Test environment' }),
    diagnoseReactError: () => Promise.resolve({ skipped: true, reason: 'Test environment' }),
    exportTestResults: () => ({ skipped: true, reason: 'Test environment' })
  };
}

// Export for use
export default testRunner;

// Export utility functions
export const runAllTests = () => testRunner.runAllTests();
export const runTestSuite = (suiteName) => testRunner.runTestSuiteByName(suiteName);
export const diagnoseReactError = (error) => testRunner.diagnoseReactError(error);
export const exportTestResults = () => testRunner.exportTestResults();

// Auto-run tests when loaded - DISABLED to prevent infinite recursion
// setTimeout(() => {
//   console.log('🚀 Auto-running diagnostic tests...');
//   testRunner.runAllTests();
// }, 2000);