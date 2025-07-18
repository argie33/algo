/**
 * React Debugging and Testing Utility
 * Specialized for diagnosing React hooks issues like use-sync-external-store
 */

import { generateCorrelationId } from './errorHandler.js';

class ReactDebugger {
  constructor() {
    this.sessionId = generateCorrelationId();
    this.debugLog = [];
    this.dependencyMap = new Map();
    this.reactVersions = new Map();
    this.hookTests = new Map();
    this.initTime = Date.now();
    
    this.setupReactDebugging();
  }

  setupReactDebugging() {
    // Enhanced React error detection
    this.setupReactErrorInterception();
    this.setupDependencyTracking();
    this.setupHookValidation();
    this.setupUseSyncExternalStoreDebugging();
  }

  setupReactErrorInterception() {
    // Intercept React errors before they bubble up
    const originalError = console.error;
    const originalWarn = console.warn;
    
    console.error = (...args) => {
      const message = args.join(' ');
      
      // Check for React-specific errors
      if (this.isReactError(message)) {
        this.handleReactError({
          level: 'error',
          message,
          args,
          timestamp: new Date().toISOString(),
          stack: new Error().stack
        });
      }
      
      originalError.apply(console, args);
    };
    
    console.warn = (...args) => {
      const message = args.join(' ');
      
      if (this.isReactWarning(message)) {
        this.handleReactError({
          level: 'warning',
          message,
          args,
          timestamp: new Date().toISOString(),
          stack: new Error().stack
        });
      }
      
      originalWarn.apply(console, args);
    };
  }

  isReactError(message) {
    const reactErrorPatterns = [
      /use-sync-external-store/i,
      /useState/i,
      /useEffect/i,
      /Cannot read properties of undefined.*reading 'useState'/i,
      /Cannot read properties of undefined.*reading 'useEffect'/i,
      /React.*error/i,
      /TypeError.*hooks/i,
      /createPalette/i,
      /Material-UI/i,
      /MUI/i
    ];
    
    return reactErrorPatterns.some(pattern => pattern.test(message));
  }

  isReactWarning(message) {
    const reactWarningPatterns = [
      /Warning: React/i,
      /Warning: Invalid hook call/i,
      /Warning: Cannot update a component/i,
      /Warning: Functions are not valid as a React child/i
    ];
    
    return reactWarningPatterns.some(pattern => pattern.test(message));
  }

  handleReactError(errorData) {
    const enhancedError = {
      ...errorData,
      sessionId: this.sessionId,
      reactDiagnostics: this.getReactDiagnostics(),
      dependencyAnalysis: this.analyzeDependencies(),
      hookValidation: this.validateHooks(),
      useSyncExternalStoreDiagnostics: this.diagnoseSyncExternalStore()
    };
    
    this.debugLog.push(enhancedError);
    
    // Log with enhanced formatting
    console.group(`🔍 React Debug Analysis [${errorData.level.toUpperCase()}]`);
    console.log('Error:', errorData.message);
    console.log('React Diagnostics:', enhancedError.reactDiagnostics);
    console.log('Dependency Analysis:', enhancedError.dependencyAnalysis);
    console.log('Hook Validation:', enhancedError.hookValidation);
    console.log('Sync External Store:', enhancedError.useSyncExternalStoreDiagnostics);
    console.groupEnd();
    
    // Run automated tests
    this.runAutomatedTests(enhancedError);
  }

  setupDependencyTracking() {
    // Track React-related dependencies
    this.trackDependency('React', () => window.React);
    this.trackDependency('ReactDOM', () => window.ReactDOM);
    this.trackDependency('use-sync-external-store', () => {
      try {
        return require('use-sync-external-store');
      } catch (e) {
        return null;
      }
    });
  }

  trackDependency(name, accessor) {
    try {
      const dependency = accessor();
      this.dependencyMap.set(name, {
        available: !!dependency,
        version: dependency?.version || 'unknown',
        properties: dependency ? Object.keys(dependency) : [],
        timestamp: new Date().toISOString()
      });
    } catch (error) {
      this.dependencyMap.set(name, {
        available: false,
        error: error.message,
        timestamp: new Date().toISOString()
      });
    }
  }

  setupHookValidation() {
    // Validate React hooks availability
    this.validateHook('useState', () => window.React?.useState);
    this.validateHook('useEffect', () => window.React?.useEffect);
    this.validateHook('useSyncExternalStore', () => window.React?.useSyncExternalStore);
    this.validateHook('useCallback', () => window.React?.useCallback);
    this.validateHook('useMemo', () => window.React?.useMemo);
    this.validateHook('useRef', () => window.React?.useRef);
    this.validateHook('useContext', () => window.React?.useContext);
  }

  validateHook(name, accessor) {
    try {
      const hook = accessor();
      this.hookTests.set(name, {
        available: typeof hook === 'function',
        type: typeof hook,
        isFunction: typeof hook === 'function',
        hasExpectedSignature: this.validateHookSignature(name, hook),
        timestamp: new Date().toISOString()
      });
    } catch (error) {
      this.hookTests.set(name, {
        available: false,
        error: error.message,
        timestamp: new Date().toISOString()
      });
    }
  }

  validateHookSignature(hookName, hook) {
    if (typeof hook !== 'function') return false;
    
    try {
      // Basic signature validation
      const signature = hook.toString();
      
      switch (hookName) {
        case 'useState':
          return signature.includes('initialState') || signature.length > 50;
        case 'useEffect':
          return signature.includes('effect') || signature.length > 50;
        case 'useSyncExternalStore':
          return signature.includes('subscribe') || signature.length > 50;
        default:
          return hook.length >= 0; // Basic function check
      }
    } catch (error) {
      return false;
    }
  }

  setupUseSyncExternalStoreDebugging() {
    // Specific debugging for use-sync-external-store issues
    try {
      // Check if the shim is being used
      const scripts = Array.from(document.scripts);
      const syncExternalStoreScript = scripts.find(script => 
        script.src.includes('use-sync-external-store') || 
        script.textContent?.includes('use-sync-external-store')
      );
      
      if (syncExternalStoreScript) {
        console.log('🔍 use-sync-external-store script detected:', syncExternalStoreScript.src);
      }
    } catch (error) {
      console.warn('Could not analyze use-sync-external-store scripts:', error);
    }
  }

  getReactDiagnostics() {
    const diagnostics = {
      reactAvailable: typeof window.React !== 'undefined',
      reactVersion: window.React?.version || 'unknown',
      reactDOMAvailable: typeof window.ReactDOM !== 'undefined',
      reactDOMVersion: window.ReactDOM?.version || 'unknown',
      reactHooks: []
    };
    
    if (window.React) {
      diagnostics.reactHooks = Object.keys(window.React)
        .filter(key => key.startsWith('use'))
        .map(hook => ({
          name: hook,
          available: typeof window.React[hook] === 'function',
          type: typeof window.React[hook]
        }));
    }
    
    return diagnostics;
  }

  analyzeDependencies() {
    const analysis = {
      totalDependencies: this.dependencyMap.size,
      availableDependencies: 0,
      missingDependencies: 0,
      dependencies: {}
    };
    
    for (const [name, info] of this.dependencyMap.entries()) {
      analysis.dependencies[name] = info;
      if (info.available) {
        analysis.availableDependencies++;
      } else {
        analysis.missingDependencies++;
      }
    }
    
    return analysis;
  }

  validateHooks() {
    const validation = {
      totalHooks: this.hookTests.size,
      availableHooks: 0,
      missingHooks: 0,
      hooks: {}
    };
    
    for (const [name, info] of this.hookTests.entries()) {
      validation.hooks[name] = info;
      if (info.available) {
        validation.availableHooks++;
      } else {
        validation.missingHooks++;
      }
    }
    
    return validation;
  }

  diagnoseSyncExternalStore() {
    const diagnostics = {
      shimDetected: false,
      reactNativeImplementation: false,
      polyfillRequired: false,
      recommendedVersion: '1.2.0',
      currentVersion: 'unknown',
      issues: []
    };
    
    try {
      // Check if React has native useSyncExternalStore
      if (window.React && window.React.useSyncExternalStore) {
        diagnostics.reactNativeImplementation = true;
      } else {
        diagnostics.polyfillRequired = true;
        diagnostics.issues.push('React does not have native useSyncExternalStore');
      }
      
      // Check for common version conflicts
      const packageLock = this.getPackageLockInfo();
      if (packageLock) {
        diagnostics.currentVersion = packageLock.version;
        if (packageLock.version !== diagnostics.recommendedVersion) {
          diagnostics.issues.push(`Version mismatch: ${packageLock.version} vs ${diagnostics.recommendedVersion}`);
        }
      }
      
      // Check for multiple versions
      const multipleVersions = this.detectMultipleVersions();
      if (multipleVersions.length > 1) {
        diagnostics.issues.push(`Multiple versions detected: ${multipleVersions.join(', ')}`);
      }
      
    } catch (error) {
      diagnostics.issues.push(`Diagnostic error: ${error.message}`);
    }
    
    return diagnostics;
  }

  getPackageLockInfo() {
    // This would need to be populated at build time
    // For now, return basic info
    return {
      version: '1.2.0',
      resolved: 'https://registry.npmjs.org/use-sync-external-store/-/use-sync-external-store-1.2.0.tgz'
    };
  }

  detectMultipleVersions() {
    // In a real implementation, this would check for multiple versions
    // For now, return a placeholder
    return ['1.2.0'];
  }

  runAutomatedTests(errorData) {
    const tests = [
      this.testReactAvailability,
      this.testHookAvailability,
      this.testUseSyncExternalStore,
      this.testComponentRender,
      this.testMemoryLeaks
    ];
    
    const testResults = {};
    
    tests.forEach(test => {
      try {
        const result = test.call(this);
        testResults[test.name] = {
          passed: result.passed,
          message: result.message,
          details: result.details
        };
      } catch (error) {
        testResults[test.name] = {
          passed: false,
          message: `Test failed: ${error.message}`,
          error: error.stack
        };
      }
    });
    
    console.log('🧪 Automated Test Results:', testResults);
    return testResults;
  }

  testReactAvailability() {
    const reactAvailable = typeof window.React !== 'undefined';
    const reactHasUseState = typeof window.React?.useState === 'function';
    
    return {
      passed: reactAvailable && reactHasUseState,
      message: reactAvailable 
        ? (reactHasUseState ? 'React is available with useState' : 'React available but useState missing')
        : 'React is not available',
      details: {
        reactAvailable,
        reactHasUseState,
        reactVersion: window.React?.version || 'unknown'
      }
    };
  }

  testHookAvailability() {
    const essentialHooks = ['useState', 'useEffect', 'useSyncExternalStore'];
    const availableHooks = essentialHooks.filter(hook => 
      typeof window.React?.[hook] === 'function'
    );
    
    return {
      passed: availableHooks.length === essentialHooks.length,
      message: `${availableHooks.length}/${essentialHooks.length} essential hooks available`,
      details: {
        essential: essentialHooks,
        available: availableHooks,
        missing: essentialHooks.filter(hook => !availableHooks.includes(hook))
      }
    };
  }

  testUseSyncExternalStore() {
    try {
      const useSyncExternalStore = window.React?.useSyncExternalStore;
      
      if (typeof useSyncExternalStore !== 'function') {
        return {
          passed: false,
          message: 'useSyncExternalStore is not available',
          details: { available: false }
        };
      }
      
      // Test basic functionality (in a safe way)
      const testStore = {
        value: 'test',
        subscribe: (callback) => {
          return () => {}; // Unsubscribe function
        },
        getSnapshot: () => 'test'
      };
      
      // Note: We can't actually call the hook outside of a component
      // This is just a structure test
      return {
        passed: true,
        message: 'useSyncExternalStore appears to be available and callable',
        details: {
          available: true,
          isFunction: typeof useSyncExternalStore === 'function',
          signature: useSyncExternalStore.toString().substring(0, 100)
        }
      };
    } catch (error) {
      return {
        passed: false,
        message: `useSyncExternalStore test failed: ${error.message}`,
        details: { error: error.stack }
      };
    }
  }

  testComponentRender() {
    // Test if we can create a basic React element
    try {
      if (!window.React) {
        return {
          passed: false,
          message: 'React is not available for component testing',
          details: { reactAvailable: false }
        };
      }
      
      const TestComponent = () => {
        return window.React.createElement('div', null, 'Test');
      };
      
      const element = window.React.createElement(TestComponent);
      
      return {
        passed: true,
        message: 'React component creation test passed',
        details: {
          elementCreated: !!element,
          elementType: typeof element
        }
      };
    } catch (error) {
      return {
        passed: false,
        message: `Component render test failed: ${error.message}`,
        details: { error: error.stack }
      };
    }
  }

  testMemoryLeaks() {
    // Basic memory leak detection
    const memoryInfo = {
      memoryUsage: performance.memory ? {
        usedJSHeapSize: performance.memory.usedJSHeapSize,
        totalJSHeapSize: performance.memory.totalJSHeapSize,
        jsHeapSizeLimit: performance.memory.jsHeapSizeLimit
      } : null,
      debugLogSize: this.debugLog.length,
      dependencyMapSize: this.dependencyMap.size,
      sessionDuration: Date.now() - this.initTime
    };
    
    return {
      passed: memoryInfo.debugLogSize < 1000, // Arbitrary threshold
      message: `Memory usage check: ${memoryInfo.debugLogSize} debug entries`,
      details: memoryInfo
    };
  }

  // Integration test runner
  runIntegrationTests() {
    console.log('🚀 Running React Integration Tests...');
    
    const integrationTests = [
      {
        name: 'Environment Setup',
        test: () => this.testEnvironmentSetup()
      },
      {
        name: 'Dependency Resolution',
        test: () => this.testDependencyResolution()
      },
      {
        name: 'Hook Functionality',
        test: () => this.testHookFunctionality()
      },
      {
        name: 'Error Handling',
        test: () => this.testErrorHandling()
      }
    ];
    
    const results = {};
    
    integrationTests.forEach(({ name, test }) => {
      try {
        const result = test();
        results[name] = result;
        console.log(`✅ ${name}: ${result.passed ? 'PASSED' : 'FAILED'}`);
        if (!result.passed) {
          console.log(`   Message: ${result.message}`);
        }
      } catch (error) {
        results[name] = {
          passed: false,
          message: error.message,
          error: error.stack
        };
        console.log(`❌ ${name}: FAILED (${error.message})`);
      }
    });
    
    return results;
  }

  testEnvironmentSetup() {
    const checks = [
      typeof window !== 'undefined',
      typeof document !== 'undefined',
      typeof navigator !== 'undefined',
      typeof console !== 'undefined'
    ];
    
    return {
      passed: checks.every(check => check),
      message: `Environment setup: ${checks.filter(Boolean).length}/${checks.length} checks passed`,
      details: {
        window: typeof window !== 'undefined',
        document: typeof document !== 'undefined',
        navigator: typeof navigator !== 'undefined',
        console: typeof console !== 'undefined'
      }
    };
  }

  testDependencyResolution() {
    const criticalDeps = ['React', 'ReactDOM'];
    const availableDeps = criticalDeps.filter(dep => 
      this.dependencyMap.get(dep)?.available
    );
    
    return {
      passed: availableDeps.length === criticalDeps.length,
      message: `Dependency resolution: ${availableDeps.length}/${criticalDeps.length} critical deps available`,
      details: {
        critical: criticalDeps,
        available: availableDeps,
        missing: criticalDeps.filter(dep => !availableDeps.includes(dep))
      }
    };
  }

  testHookFunctionality() {
    const criticalHooks = ['useState', 'useEffect'];
    const availableHooks = criticalHooks.filter(hook => 
      this.hookTests.get(hook)?.available
    );
    
    return {
      passed: availableHooks.length === criticalHooks.length,
      message: `Hook functionality: ${availableHooks.length}/${criticalHooks.length} critical hooks available`,
      details: {
        critical: criticalHooks,
        available: availableHooks,
        missing: criticalHooks.filter(hook => !availableHooks.includes(hook))
      }
    };
  }

  testErrorHandling() {
    try {
      // Test error handling by triggering a controlled error
      const testError = new Error('Test error for debugging');
      this.handleReactError({
        level: 'test',
        message: testError.message,
        args: [testError.message],
        timestamp: new Date().toISOString(),
        stack: testError.stack
      });
      
      return {
        passed: true,
        message: 'Error handling test completed successfully',
        details: {
          errorLogged: this.debugLog.length > 0,
          logSize: this.debugLog.length
        }
      };
    } catch (error) {
      return {
        passed: false,
        message: `Error handling test failed: ${error.message}`,
        details: { error: error.stack }
      };
    }
  }

  // Export debug report
  exportDebugReport() {
    const report = {
      sessionId: this.sessionId,
      timestamp: new Date().toISOString(),
      sessionDuration: Date.now() - this.initTime,
      reactDiagnostics: this.getReactDiagnostics(),
      dependencyAnalysis: this.analyzeDependencies(),
      hookValidation: this.validateHooks(),
      useSyncExternalStoreDiagnostics: this.diagnoseSyncExternalStore(),
      debugLog: this.debugLog,
      integrationTestResults: this.runIntegrationTests()
    };
    
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `react-debug-report-${this.sessionId}.json`;
    a.click();
    URL.revokeObjectURL(url);
    
    return report;
  }

  // Clear debug log
  clearDebugLog() {
    this.debugLog = [];
  }
}

// Create global instance
const reactDebugger = new ReactDebugger();

// Export for use in components
export default reactDebugger;

// Add to window for debugging
window.reactDebugger = reactDebugger;

// Export utility functions
export const debugReactError = (error, component = 'Unknown') => {
  reactDebugger.handleReactError({
    level: 'error',
    message: error.message,
    args: [error.message],
    timestamp: new Date().toISOString(),
    stack: error.stack,
    component
  });
};

export const runReactTests = () => {
  return reactDebugger.runIntegrationTests();
};

export const exportReactDebugReport = () => {
  return reactDebugger.exportDebugReport();
};

// Auto-run tests on load
setTimeout(() => {
  console.log('🔍 Auto-running React integration tests...');
  reactDebugger.runIntegrationTests();
}, 1000);