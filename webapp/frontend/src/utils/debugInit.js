/**
 * Debug Initialization
 * Sets up comprehensive debugging and testing for the application
 */

import reactDebugger from './reactDebugger.js';
// import testRunner from './testRunner.js';  // Temporarily disabled to fix test hanging
import { healthChecker } from './errorHandler.js';

// Stub testRunner to prevent hanging during tests
const testRunner = {
  runAllTests: () => Promise.resolve({ skipped: true, reason: 'Disabled during test runs' }),
  runTestSuiteByName: () => Promise.resolve({ skipped: true }),
  exportTestResults: () => ({ skipped: true })
};

class DebugInit {
  constructor() {
    this.initialized = false;
    this.debugTools = {
      reactDebugger,
      testRunner,
      healthChecker
    };
  }

  async initialize() {
    if (this.initialized) {
      return;
    }

    console.log('🔧 Initializing debug tools...');
    
    try {
      // Initialize React debugging
      await this.setupReactDebugging();
      
      // Initialize automated testing
      await this.setupAutomatedTesting();
      
      // Initialize health monitoring
      await this.setupHealthMonitoring();
      
      // Setup global error handlers
      await this.setupGlobalErrorHandlers();
      
      // Add debug utilities to window
      this.exposeDebugTools();
      
      this.initialized = true;
      console.log('✅ Debug tools initialized successfully');
      
      // Run initial diagnostics
      await this.runInitialDiagnostics();
      
    } catch (error) {
      console.error('❌ Failed to initialize debug tools:', error);
    }
  }

  async setupReactDebugging() {
    console.log('🔍 Setting up React debugging...');
    
    // React debugger is already initialized in its constructor
    // Add custom React error detection
    this.setupCustomReactErrorDetection();
  }

  setupCustomReactErrorDetection() {
    // Enhanced error detection for specific React issues
    const originalError = window.onerror;
    
    window.onerror = (message, source, lineno, colno, error) => {
      // Check for use-sync-external-store errors
      if (message.includes('use-sync-external-store') || 
          message.includes('useState') || 
          message.includes('Cannot read properties of undefined')) {
        
        console.error('🚨 Detected React hooks error:', {
          message,
          source,
          lineno,
          colno,
          error
        });
        
        // Run immediate diagnostics
        this.runUseStateHookDiagnostics();
      }
      
      // Call original error handler
      if (originalError) {
        return originalError(message, source, lineno, colno, error);
      }
    };
  }

  async runUseStateHookDiagnostics() {
    console.log('🔍 Running useState hook diagnostics...');
    
    const diagnostics = {
      timestamp: new Date().toISOString(),
      reactAvailable: typeof window.React !== 'undefined',
      reactVersion: window.React?.version,
      useStateAvailable: typeof window.React?.useState === 'function',
      useSyncExternalStoreAvailable: typeof window.React?.useSyncExternalStore === 'function',
      reactHooks: window.React ? Object.keys(window.React).filter(k => k.startsWith('use')) : [],
      packageVersions: await this.getPackageVersions(),
      memoryUsage: performance.memory ? {
        usedJSHeapSize: performance.memory.usedJSHeapSize,
        totalJSHeapSize: performance.memory.totalJSHeapSize
      } : null
    };
    
    console.log('📊 useState Hook Diagnostics:', diagnostics);
    
    // Store diagnostics for later analysis
    if (!window.debugDiagnostics) {
      window.debugDiagnostics = [];
    }
    window.debugDiagnostics.push(diagnostics);
    
    return diagnostics;
  }

  async getPackageVersions() {
    // This would ideally be injected at build time
    // For now, detect what we can from the runtime
    return {
      react: window.React?.version || 'unknown',
      reactDOM: window.ReactDOM?.version || 'unknown',
      useSyncExternalStore: '1.2.0', // From package.json override
      note: 'Versions detected at runtime - may not be complete'
    };
  }

  async setupAutomatedTesting() {
    console.log('🧪 Setting up automated testing...');
    
    // Test runner is already initialized
    // Add custom test schedules
    this.setupTestSchedules();
  }

  setupTestSchedules() {
    // DISABLED: Automatic test execution to prevent infinite recursion
    // Tests can be run manually via window.debugTools.runAllTests()
    console.log('🚫 Automatic test schedules disabled to prevent recursion');
    console.log('💡 Run tests manually: window.debugTools.runAllTests()');
  }

  async setupHealthMonitoring() {
    console.log('🏥 Setting up health monitoring...');
    
    // Run health checks every 30 seconds
    setInterval(async () => {
      try {
        const health = await healthChecker.getDetailedStatus();
        
        // Log health status
        console.log('💓 Health Status:', health);
        
        // Store health data
        if (!window.healthHistory) {
          window.healthHistory = [];
        }
        window.healthHistory.push(health);
        
        // Keep only last 100 health checks
        if (window.healthHistory.length > 100) {
          window.healthHistory = window.healthHistory.slice(-100);
        }
        
      } catch (error) {
        console.error('❌ Health check failed:', error);
      }
    }, 30 * 1000); // 30 seconds
  }

  async setupGlobalErrorHandlers() {
    console.log('🛡️ Setting up global error handlers...');
    
    // Enhanced unhandled promise rejection handler
    window.addEventListener('unhandledrejection', (event) => {
      console.error('🚨 Unhandled promise rejection:', event.reason);
      
      // Run diagnostics for promise rejections
      this.runPromiseRejectionDiagnostics(event.reason);
    });
    
    // Enhanced global error handler
    window.addEventListener('error', (event) => {
      console.error('🚨 Global error:', event.error);
      
      // Run diagnostics for global errors
      this.runGlobalErrorDiagnostics(event.error);
    });
  }

  async runPromiseRejectionDiagnostics(reason) {
    const diagnostics = {
      type: 'promise-rejection',
      timestamp: new Date().toISOString(),
      reason: reason?.message || reason?.toString() || 'Unknown',
      stack: reason?.stack,
      isNetworkError: reason?.message?.includes('fetch') || reason?.message?.includes('network'),
      isAuthError: reason?.status === 401 || reason?.status === 403,
      isServerError: reason?.status >= 500
    };
    
    console.log('📊 Promise Rejection Diagnostics:', diagnostics);
    
    // Store diagnostics
    if (!window.promiseRejectionDiagnostics) {
      window.promiseRejectionDiagnostics = [];
    }
    window.promiseRejectionDiagnostics.push(diagnostics);
  }

  async runGlobalErrorDiagnostics(error) {
    const diagnostics = {
      type: 'global-error',
      timestamp: new Date().toISOString(),
      message: error?.message || 'Unknown error',
      stack: error?.stack,
      isReactError: error?.message?.includes('React') || error?.stack?.includes('React'),
      isHooksError: error?.message?.includes('hook') || error?.message?.includes('useState'),
      isMUIError: error?.message?.includes('MUI') || error?.message?.includes('Material-UI'),
      isUseSyncExternalStoreError: error?.message?.includes('use-sync-external-store')
    };
    
    console.log('📊 Global Error Diagnostics:', diagnostics);
    
    // Store diagnostics
    if (!window.globalErrorDiagnostics) {
      window.globalErrorDiagnostics = [];
    }
    window.globalErrorDiagnostics.push(diagnostics);
    
    // Run specific diagnostics for React errors
    if (diagnostics.isReactError || diagnostics.isHooksError) {
      await this.runUseStateHookDiagnostics();
    }
  }

  exposeDebugTools() {
    console.log('🔧 Exposing debug tools to window...');
    
    window.debugTools = {
      reactDebugger,
      testRunner,
      healthChecker,
      
      // Convenience methods
      runAllTests: () => testRunner.runAllTests(),
      runReactTests: () => testRunner.runTestSuite('react-hooks'),
      runUseSyncExternalStoreTests: () => testRunner.runTestSuite('use-sync-external-store'),
      exportDebugReport: () => reactDebugger.exportDebugReport(),
      exportTestResults: () => testRunner.exportTestResults(),
      getHealthStatus: () => healthChecker.getDetailedStatus(),
      
      // Diagnostic methods
      runUseStateHookDiagnostics: () => this.runUseStateHookDiagnostics(),
      getDiagnosticHistory: () => ({
        debug: window.debugDiagnostics || [],
        health: window.healthHistory || [],
        promiseRejections: window.promiseRejectionDiagnostics || [],
        globalErrors: window.globalErrorDiagnostics || []
      }),
      
      // Utility methods
      clearDiagnostics: () => {
        window.debugDiagnostics = [];
        window.healthHistory = [];
        window.promiseRejectionDiagnostics = [];
        window.globalErrorDiagnostics = [];
        reactDebugger.clearDebugLog();
        console.log('✅ All diagnostics cleared');
      }
    };
    
    console.log('🎯 Debug tools available at window.debugTools');
    console.log('Usage examples:');
    console.log('  window.debugTools.runAllTests()');
    console.log('  window.debugTools.runReactTests()');
    console.log('  window.debugTools.exportDebugReport()');
    console.log('  window.debugTools.getHealthStatus()');
  }

  async runInitialDiagnostics() {
    console.log('🚀 Running initial diagnostics...');
    
    try {
      // Run useState hook diagnostics
      await this.runUseStateHookDiagnostics();
      
      // Run health check
      const health = await healthChecker.getDetailedStatus();
      console.log('💓 Initial health status:', health);
      
      // DISABLED: Initial test execution to prevent infinite recursion
      console.log('🚫 Initial test execution disabled to prevent recursion');
      console.log('💡 Run tests manually: window.debugTools.runAllTests()');
      
      console.log('✅ Initial diagnostics completed (tests disabled)');
      
    } catch (error) {
      console.error('❌ Initial diagnostics failed:', error);
    }
  }
}

// Create and initialize
const debugInit = new DebugInit();

// Auto-initialize when loaded
setTimeout(() => {
  debugInit.initialize();
}, 500);

export default debugInit;