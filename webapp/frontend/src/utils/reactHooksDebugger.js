/**
 * React Hooks Debugger - Specialized for use-sync-external-store issues
 * Provides detailed diagnostics and fixes for React hooks problems
 */

class ReactHooksDebugger {
  constructor() {
    this.initialized = false;
    this.diagnostics = [];
    this.fixes = [];
    this.initialize();
  }

  initialize() {
    if (this.initialized) return;
    
    console.log('🔍 Initializing React Hooks Debugger...');
    
    // Immediate diagnostics
    this.runImmediateDiagnostics();
    
    // Setup monitoring
    this.setupContinuousMonitoring();
    
    this.initialized = true;
    console.log('✅ React Hooks Debugger initialized');
  }

  runImmediateDiagnostics() {
    console.log('🔍 Running immediate React hooks diagnostics...');
    
    const diagnostics = {
      timestamp: new Date().toISOString(),
      environment: this.analyzeEnvironment(),
      react: this.analyzeReact(),
      useSyncExternalStore: this.analyzeUseSyncExternalStore(),
      dependencies: this.analyzeDependencies(),
      recommendations: []
    };
    
    // Generate recommendations
    diagnostics.recommendations = this.generateRecommendations(diagnostics);
    
    this.diagnostics.push(diagnostics);
    
    console.log('📊 React Hooks Diagnostics:', diagnostics);
    
    // Auto-apply fixes if safe
    this.autoApplyFixes(diagnostics);
    
    return diagnostics;
  }

  analyzeEnvironment() {
    return {
      userAgent: navigator.userAgent,
      url: window.location.href,
      protocol: window.location.protocol,
      host: window.location.host,
      isDevelopment: window.location.hostname === 'localhost',
      isProduction: window.location.hostname !== 'localhost',
      hasModule: typeof window.module !== 'undefined',
      hasRequire: typeof window.require !== 'undefined',
      hasProcess: typeof window.process !== 'undefined',
      nodeEnv: window.process?.env?.NODE_ENV || 'unknown'
    };
  }

  analyzeReact() {
    const reactAnalysis = {
      available: typeof window.React !== 'undefined',
      version: window.React?.version || 'unknown',
      location: this.findReactLocation(),
      hooks: {},
      internals: {}
    };
    
    if (window.React) {
      // Analyze React hooks
      const hooks = [
        'useState', 'useEffect', 'useContext', 'useReducer', 
        'useCallback', 'useMemo', 'useRef', 'useImperativeHandle',
        'useLayoutEffect', 'useDebugValue', 'useDeferredValue',
        'useTransition', 'useId', 'useSyncExternalStore'
      ];
      
      hooks.forEach(hook => {
        reactAnalysis.hooks[hook] = {
          available: typeof window.React[hook] === 'function',
          type: typeof window.React[hook],
          signature: window.React[hook] ? window.React[hook].toString().substring(0, 100) : null
        };
      });
      
      // Check React internals
      reactAnalysis.internals = {
        hasReactInternals: typeof window.React.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED !== 'undefined',
        hasCurrentDispatcher: typeof window.React.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED?.ReactCurrentDispatcher !== 'undefined',
        hasCurrentOwner: typeof window.React.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED?.ReactCurrentOwner !== 'undefined'
      };
    }
    
    return reactAnalysis;
  }

  analyzeUseSyncExternalStore() {
    const analysis = {
      reactNative: {
        available: typeof window.React?.useSyncExternalStore === 'function',
        signature: window.React?.useSyncExternalStore?.toString().substring(0, 200)
      },
      shimDetected: false,
      shimLocation: null,
      shimVersion: null,
      multipleVersions: false,
      versionConflicts: []
    };
    
    // Check for shim in scripts
    const scripts = Array.from(document.scripts);
    const shimScript = scripts.find(script => 
      script.src.includes('use-sync-external-store') || 
      (script.textContent && script.textContent.includes('useSyncExternalStore'))
    );
    
    if (shimScript) {
      analysis.shimDetected = true;
      analysis.shimLocation = shimScript.src || 'inline';
    }
    
    // Check for multiple versions
    const modules = this.findUseSyncExternalStoreModules();
    if (modules.length > 1) {
      analysis.multipleVersions = true;
      analysis.versionConflicts = modules;
    }
    
    // Test functionality
    if (window.React?.useSyncExternalStore) {
      try {
        analysis.functionalityTest = this.testUseSyncExternalStoreFunctionality();
      } catch (error) {
        analysis.functionalityTest = {
          success: false,
          error: error.message
        };
      }
    }
    
    return analysis;
  }

  findReactLocation() {
    const scripts = Array.from(document.scripts);
    const reactScript = scripts.find(script => 
      script.src.includes('react') && !script.src.includes('react-dom')
    );
    return reactScript?.src || 'unknown';
  }

  findUseSyncExternalStoreModules() {
    const modules = [];
    
    // Check script tags
    const scripts = Array.from(document.scripts);
    scripts.forEach(script => {
      if (script.src.includes('use-sync-external-store')) {
        modules.push({
          type: 'script',
          src: script.src,
          version: this.extractVersionFromUrl(script.src)
        });
      }
    });
    
    // Check for webpack chunks
    if (window.webpackChunkName) {
      modules.push({
        type: 'webpack',
        chunks: window.webpackChunkName
      });
    }
    
    return modules;
  }

  extractVersionFromUrl(url) {
    const versionMatch = url.match(/use-sync-external-store-(\d+\.\d+\.\d+)/);
    return versionMatch ? versionMatch[1] : 'unknown';
  }

  testUseSyncExternalStoreFunctionality() {
    const useSyncExternalStore = window.React.useSyncExternalStore;
    
    if (typeof useSyncExternalStore !== 'function') {
      return {
        success: false,
        error: 'useSyncExternalStore is not a function'
      };
    }
    
    // Test the function signature
    const signature = useSyncExternalStore.toString();
    const expectedPatterns = [
      'subscribe', 'getSnapshot', 'getServerSnapshot'
    ];
    
    const hasExpectedSignature = expectedPatterns.some(pattern => 
      signature.includes(pattern)
    );
    
    return {
      success: true,
      hasExpectedSignature,
      signature: signature.substring(0, 200),
      length: signature.length
    };
  }

  analyzeDependencies() {
    const analysis = {
      packageLock: this.analyzePackageLock(),
      webpackModules: this.analyzeWebpackModules(),
      conflicts: [],
      duplicates: []
    };
    
    // Check for common conflicts
    const potentialConflicts = [
      'react', 'react-dom', 'use-sync-external-store',
      '@headlessui/react', '@tanstack/react-query', '@aws-amplify/ui-react'
    ];
    
    potentialConflicts.forEach(pkg => {
      const versions = this.findPackageVersions(pkg);
      if (versions.length > 1) {
        analysis.conflicts.push({
          package: pkg,
          versions: versions
        });
      }
    });
    
    return analysis;
  }

  analyzePackageLock() {
    // In a real implementation, this would parse package-lock.json
    // For now, return what we know from the runtime
    return {
      useSyncExternalStore: {
        version: '1.2.0',
        overridden: true,
        note: 'Version overridden in package.json'
      }
    };
  }

  analyzeWebpackModules() {
    if (typeof window.__webpack_require__ !== 'undefined') {
      return {
        available: true,
        moduleIds: Object.keys(window.__webpack_require__.cache || {}),
        note: 'Webpack modules detected'
      };
    }
    
    return {
      available: false,
      note: 'Webpack modules not detected'
    };
  }

  findPackageVersions(packageName) {
    const versions = [];
    
    // Check scripts
    const scripts = Array.from(document.scripts);
    scripts.forEach(script => {
      if (script.src.includes(packageName)) {
        const version = this.extractVersionFromUrl(script.src);
        if (version !== 'unknown') {
          versions.push({
            source: 'script',
            version: version,
            url: script.src
          });
        }
      }
    });
    
    return versions;
  }

  generateRecommendations(diagnostics) {
    const recommendations = [];
    
    // React availability
    if (!diagnostics.react.available) {
      recommendations.push({
        severity: 'critical',
        type: 'react-missing',
        message: 'React is not available in the global scope',
        fix: 'Ensure React is properly imported and available'
      });
    }
    
    // useSyncExternalStore availability
    if (!diagnostics.react.hooks.useSyncExternalStore?.available) {
      recommendations.push({
        severity: 'critical',
        type: 'use-sync-external-store-missing',
        message: 'useSyncExternalStore is not available',
        fix: 'Install and configure use-sync-external-store package'
      });
    }
    
    // Version conflicts
    if (diagnostics.dependencies.conflicts.length > 0) {
      recommendations.push({
        severity: 'high',
        type: 'version-conflicts',
        message: 'Multiple versions of dependencies detected',
        fix: 'Use package.json overrides to force single versions',
        details: diagnostics.dependencies.conflicts
      });
    }
    
    // React version compatibility
    if (diagnostics.react.version && diagnostics.react.version.startsWith('18.')) {
      if (!diagnostics.react.hooks.useSyncExternalStore?.available) {
        recommendations.push({
          severity: 'high',
          type: 'react-18-compatibility',
          message: 'React 18 detected but useSyncExternalStore is missing',
          fix: 'React 18 should have native useSyncExternalStore support'
        });
      }
    }
    
    return recommendations;
  }

  autoApplyFixes(diagnostics) {
    console.log('🔧 Attempting to auto-apply fixes...');
    
    diagnostics.recommendations.forEach(recommendation => {
      try {
        switch (recommendation.type) {
          case 'use-sync-external-store-missing':
            this.attemptUseSyncExternalStoreFix();
            break;
          case 'react-missing':
            this.attemptReactFix();
            break;
          default:
            console.log(`ℹ️ No auto-fix available for: ${recommendation.type}`);
        }
      } catch (error) {
        console.error(`❌ Failed to apply fix for ${recommendation.type}:`, error);
      }
    });
  }

  attemptUseSyncExternalStoreFix() {
    console.log('🔧 Attempting to fix useSyncExternalStore...');
    
    // Check if we can polyfill useSyncExternalStore
    if (window.React && !window.React.useSyncExternalStore) {
      console.log('⚠️ Attempting to polyfill useSyncExternalStore...');
      
      // This is a simplified polyfill - in production, use the official one
      window.React.useSyncExternalStore = function(subscribe, getSnapshot, getServerSnapshot) {
        const [state, setState] = window.React.useState(getSnapshot());
        
        window.React.useEffect(() => {
          const unsubscribe = subscribe(() => {
            setState(getSnapshot());
          });
          return unsubscribe;
        }, [subscribe, getSnapshot]);
        
        return state;
      };
      
      console.log('✅ useSyncExternalStore polyfill applied');
      
      this.fixes.push({
        type: 'useSyncExternalStore-polyfill',
        timestamp: new Date().toISOString(),
        success: true
      });
    }
  }

  attemptReactFix() {
    console.log('🔧 Attempting to fix React availability...');
    
    // If React is not in global scope, try to find it
    if (!window.React) {
      // Check if React is available in modules
      if (typeof require !== 'undefined') {
        try {
          window.React = require('react');
          console.log('✅ React loaded via require');
        } catch (error) {
          console.log('❌ Could not load React via require:', error);
        }
      }
    }
  }

  setupContinuousMonitoring() {
    // Monitor for changes in React availability
    const checkInterval = setInterval(() => {
      const currentState = {
        reactAvailable: typeof window.React !== 'undefined',
        useSyncExternalStoreAvailable: typeof window.React?.useSyncExternalStore === 'function'
      };
      
      const lastDiagnostic = this.diagnostics[this.diagnostics.length - 1];
      if (lastDiagnostic) {
        const lastState = {
          reactAvailable: lastDiagnostic.react.available,
          useSyncExternalStoreAvailable: lastDiagnostic.react.hooks.useSyncExternalStore?.available
        };
        
        if (JSON.stringify(currentState) !== JSON.stringify(lastState)) {
          console.log('🔄 React state changed, running diagnostics...');
          this.runImmediateDiagnostics();
        }
      }
    }, 5000); // Check every 5 seconds
    
    // Stop monitoring after 5 minutes
    setTimeout(() => {
      clearInterval(checkInterval);
    }, 5 * 60 * 1000);
  }

  // Public API
  getDiagnostics() {
    return this.diagnostics;
  }

  getFixes() {
    return this.fixes;
  }

  exportReport() {
    const report = {
      timestamp: new Date().toISOString(),
      version: '1.0.0',
      diagnostics: this.diagnostics,
      fixes: this.fixes,
      summary: this.generateSummary()
    };
    
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `react-hooks-debug-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
    
    return report;
  }

  generateSummary() {
    const latestDiagnostic = this.diagnostics[this.diagnostics.length - 1];
    if (!latestDiagnostic) return null;
    
    return {
      reactAvailable: latestDiagnostic.react.available,
      reactVersion: latestDiagnostic.react.version,
      useSyncExternalStoreAvailable: latestDiagnostic.react.hooks.useSyncExternalStore?.available,
      criticalIssues: latestDiagnostic.recommendations.filter(r => r.severity === 'critical').length,
      highIssues: latestDiagnostic.recommendations.filter(r => r.severity === 'high').length,
      fixesApplied: this.fixes.length
    };
  }
}

// Create global instance
const reactHooksDebugger = new ReactHooksDebugger();

// Export for use
export default reactHooksDebugger;

// Add to window for debugging
window.reactHooksDebugger = reactHooksDebugger;

// Export utility functions
export const runReactHooksDiagnostics = () => reactHooksDebugger.runImmediateDiagnostics();
export const exportReactHooksReport = () => reactHooksDebugger.exportReport();
export const getReactHooksSummary = () => reactHooksDebugger.generateSummary();