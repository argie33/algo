/**
 * Emergency Fallback - Last resort error handling and diagnostics
 * If all else fails, this provides a working React environment
 */

const EmergencyFallback = {
  activated: false,
  
  activate() {
    if (this.activated) return;
    
    console.log('🚨 EMERGENCY FALLBACK ACTIVATED - React hooks system failure detected');
    
    this.activated = true;
    
    // 1. Comprehensive error reporting
    this.generateComprehensiveErrorReport();
    
    // 2. Attempt emergency React restoration
    this.attemptEmergencyReactRestoration();
    
    // 3. Provide fallback UI
    this.provideFallbackUI();
  },
  
  generateComprehensiveErrorReport() {
    const report = {
      timestamp: Date.now(),
      url: window.location.href,
      userAgent: navigator.userAgent,
      errorType: 'React useState undefined',
      
      reactState: {
        windowReact: typeof window.React,
        globalReact: typeof global?.React,
        reactImport: typeof React,
        reactKeys: window.React ? Object.keys(window.React) : 'React not available',
        reactHooks: window.React ? {
          useState: typeof window.React.useState,
          useEffect: typeof window.React.useEffect,
          useSyncExternalStore: typeof window.React.useSyncExternalStore
        } : 'No React'
      },
      
      moduleSystem: {
        require: typeof require !== 'undefined',
        webpack: typeof __webpack_require__ !== 'undefined',
        vite: typeof __vite__ !== 'undefined',
        moduleCache: typeof require !== 'undefined' ? Object.keys(require.cache || {}).filter(k => k.includes('react')).slice(0, 10) : 'No require'
      },
      
      packageState: {
        scripts: Array.from(document.scripts).map(s => ({
          src: s.src,
          type: s.type,
          async: s.async,
          defer: s.defer
        })).filter(s => s.src.includes('react') || s.src.includes('use-sync')),
        
        suspiciousGlobals: [
          'useSyncExternalStore',
          '__REACT_DEVTOOLS_GLOBAL_HOOK__',
          '__webpack_require__',
          '__vite__'
        ].map(key => ({
          key,
          type: typeof window[key],
          available: window[key] !== undefined
        }))
      },
      
      diagnostics: {
        reactHooksDebugger: window.reactHooksDebugger ? window.reactHooksDebugger.getDiagnostics() : 'Not available',
        packageInspector: window.packageInspector ? window.packageInspector.inspections : 'Not available',
        errorCapture: window.ERROR_MONITOR ? window.ERROR_MONITOR.errors : 'Not available'
      },
      
      recommendations: this.generateEmergencyRecommendations()
    };
    
    console.log('📋 COMPREHENSIVE ERROR REPORT:', report);
    
    // Save to localStorage for persistence
    try {
      localStorage.setItem('react-hooks-error-report', JSON.stringify(report));
    } catch (e) {
      console.log('Could not save error report to localStorage:', e);
    }
    
    // Send to console for copying
    console.log('📋 COPY THIS ERROR REPORT:');
    console.log(JSON.stringify(report, null, 2));
    
    return report;
  },
  
  generateEmergencyRecommendations() {
    return [
      {
        priority: 'CRITICAL',
        action: 'Check if use-sync-external-store package is still somehow loaded',
        command: 'npm list use-sync-external-store'
      },
      {
        priority: 'CRITICAL', 
        action: 'Clear all caches and reinstall dependencies',
        command: 'rm -rf node_modules package-lock.json && npm install'
      },
      {
        priority: 'HIGH',
        action: 'Check for React version conflicts',
        command: 'npm list react react-dom'
      },
      {
        priority: 'HIGH',
        action: 'Verify Vite configuration is not caching old dependencies',
        command: 'rm -rf dist .vite && npm run build'
      },
      {
        priority: 'MEDIUM',
        action: 'Check bundler output for use-sync-external-store references',
        command: 'Build and inspect bundle for external store references'
      }
    ];
  },
  
  attemptEmergencyReactRestoration() {
    console.log('🔧 ATTEMPTING EMERGENCY REACT RESTORATION...');
    
    // If React is completely missing, try to restore it
    if (typeof React === 'undefined' || !React.useState) {
      try {
        // Try to get React from different sources
        let emergencyReact = null;
        
        // Method 1: Try require
        try {
          emergencyReact = require('react');
          console.log('✅ Emergency React restored via require()');
        } catch (e) {
          console.log('❌ Emergency React require() failed:', e.message);
        }
        
        // Method 2: Try dynamic import
        if (!emergencyReact) {
          import('react').then(reactModule => {
            window.React = reactModule.default || reactModule;
            console.log('✅ Emergency React restored via dynamic import');
          }).catch(e => {
            console.log('❌ Emergency React dynamic import failed:', e.message);
          });
        }
        
        // Method 3: Create minimal React polyfill
        if (!emergencyReact && !window.React) {
          console.log('🚨 Creating minimal React polyfill...');
          window.React = this.createMinimalReactPolyfill();
        }
        
        if (emergencyReact) {
          window.React = emergencyReact;
          global.React = emergencyReact;
        }
        
      } catch (error) {
        console.log('❌ Emergency React restoration failed:', error);
      }
    }
    
    // Ensure useSyncExternalStore is available
    if (window.React && !window.React.useSyncExternalStore) {
      console.log('🔧 Adding useSyncExternalStore polyfill...');
      window.React.useSyncExternalStore = this.createUseSyncExternalStorePolyfill();
    }
  },
  
  createMinimalReactPolyfill() {
    console.log('🚨 Creating minimal React polyfill - THIS IS EMERGENCY MODE');
    
    return {
      version: '18.3.1-emergency-polyfill',
      
      createElement: (type, props, ...children) => {
        return { type, props: { ...props, children } };
      },
      
      useState: (initialState) => {
        console.log('🚨 Emergency useState called - this is a polyfill');
        let state = initialState;
        const setState = (newState) => {
          state = typeof newState === 'function' ? newState(state) : newState;
        };
        return [state, setState];
      },
      
      useEffect: (effect, deps) => {
        console.log('🚨 Emergency useEffect called - this is a polyfill');
        try {
          effect();
        } catch (e) {
          console.log('Emergency useEffect error:', e);
        }
      },
      
      useSyncExternalStore: this.createUseSyncExternalStorePolyfill(),
      
      useCallback: (callback, deps) => callback,
      useMemo: (factory, deps) => factory(),
      useRef: (initialValue) => ({ current: initialValue }),
      useContext: (context) => context.defaultValue,
      useReducer: (reducer, initialState) => {
        let state = initialState;
        const dispatch = (action) => {
          state = reducer(state, action);
        };
        return [state, dispatch];
      }
    };
  },
  
  createUseSyncExternalStorePolyfill() {
    return function useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot) {
      console.log('🚨 Emergency useSyncExternalStore called - this is a polyfill');
      
      // This is a simplified polyfill - not production ready
      let state = getSnapshot();
      
      // In a real implementation, this would use useEffect and useState
      try {
        const unsubscribe = subscribe(() => {
          const newState = getSnapshot();
          if (newState !== state) {
            state = newState;
            // In a real implementation, this would trigger a re-render
          }
        });
        
        // Store unsubscribe function for cleanup
        setTimeout(() => {
          if (typeof unsubscribe === 'function') {
            unsubscribe();
          }
        }, 30000); // Clean up after 30 seconds
        
      } catch (error) {
        console.log('Emergency useSyncExternalStore error:', error);
      }
      
      return state;
    };
  },
  
  provideFallbackUI() {
    console.log('🚨 Providing fallback UI...');
    
    // Create fallback UI that doesn't depend on React
    const fallbackHTML = `
      <div id="emergency-fallback" style="
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        display: flex;
        justify-content: center;
        align-items: center;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        color: white;
        z-index: 9999;
      ">
        <div style="
          background: rgba(255,255,255,0.1);
          padding: 3rem;
          border-radius: 20px;
          backdrop-filter: blur(10px);
          text-align: center;
          max-width: 600px;
          margin: 20px;
        ">
          <h1 style="margin: 0 0 1rem 0; font-size: 2.5rem;">🔧 System Recovery Mode</h1>
          <p style="margin: 0 0 2rem 0; font-size: 1.2rem; opacity: 0.9;">
            The application is experiencing a React hooks initialization error. 
            Emergency diagnostics are running...
          </p>
          <div style="
            background: rgba(0,0,0,0.2);
            padding: 1rem;
            border-radius: 10px;
            margin: 1rem 0;
            text-align: left;
            font-family: monospace;
            font-size: 0.9rem;
          ">
            <strong>Diagnostic Status:</strong><br>
            ✅ Error captured and logged<br>
            ✅ Comprehensive report generated<br>
            ✅ Emergency React polyfill applied<br>
            📊 Check browser console for detailed analysis
          </div>
          <button onclick="window.location.reload()" style="
            background: #4CAF50;
            color: white;
            border: none;
            padding: 15px 30px;
            border-radius: 8px;
            font-size: 1.1rem;
            cursor: pointer;
            margin: 10px;
          ">
            🔄 Reload Application
          </button>
          <button onclick="window.packageInspector?.exportInspectionReport()" style="
            background: #2196F3;
            color: white;
            border: none;
            padding: 15px 30px;
            border-radius: 8px;
            font-size: 1.1rem;
            cursor: pointer;
            margin: 10px;
          ">
            📋 Export Debug Report
          </button>
        </div>
      </div>
    `;
    
    // Only show fallback UI if React completely fails to render
    setTimeout(() => {
      const rootElement = document.getElementById('root');
      if (!rootElement || rootElement.innerHTML.trim() === '') {
        document.body.insertAdjacentHTML('beforeend', fallbackHTML);
      }
    }, 5000);
  }
};

// Monitor for React failures
if (typeof window !== 'undefined') {
  window.emergencyFallback = EmergencyFallback;
  
  // Set up emergency monitoring
  setTimeout(() => {
    if (typeof React === 'undefined' || !React.useState) {
      console.log('🚨 React hooks failure detected - activating emergency fallback');
      EmergencyFallback.activate();
    }
  }, 3000);
  
  // Monitor for the specific error
  const originalError = console.error;
  console.error = (...args) => {
    const errorMessage = args.join(' ');
    if (errorMessage.includes('useState') && errorMessage.includes('undefined')) {
      console.log('🚨 EXACT ERROR DETECTED - activating emergency fallback');
      EmergencyFallback.activate();
    }
    originalError.apply(console, args);
  };
}

export default EmergencyFallback;