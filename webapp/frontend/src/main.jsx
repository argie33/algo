// CRITICAL: Initialize React state FIRST to prevent use-sync-external-store errors
import './utils/reactStateInitializer.js'

// CRITICAL: Load React module preloader FIRST to prevent use-sync-external-store errors
import './utils/reactModulePreloader.js'

// CRITICAL: Apply React hooks patch IMMEDIATELY after React is preloaded
import './utils/reactHooksPatch.js'

// ENHANCED ERROR TRACING: Load debugger to capture the exact error
import './utils/reactHooksDebugger.js'

// COMPREHENSIVE PACKAGE ANALYSIS: Track dependencies and conflicts
import './utils/packageInspector.js'

// EMERGENCY FALLBACK: Last resort error handling and recovery
import './utils/emergencyFallback.js'

// CRITICAL LOGGING: Track import order and React state
console.log('🔍 MAIN.JSX LOADING - React state check:', {
  timestamp: Date.now(),
  reactAvailable: typeof React !== 'undefined',
  windowReact: typeof window?.React !== 'undefined',
  globalReact: typeof global?.React !== 'undefined'
});

// Initialize essential utilities AFTER React is properly preloaded
import './utils/browserCompatibility.js'
import asyncErrorHandler from './utils/asyncErrorHandler.js'
import memoryLeakPrevention from './utils/memoryLeakPrevention.js'
import performanceMonitor from './utils/performanceMonitor.js'

// Debug utilities - will be loaded conditionally after React initialization

// Re-import React after preloader (should be the same instance due to module caching)
import React from 'react'
import ReactDOM from 'react-dom/client'

console.log('✅ React imported after preloader - hooks available:', {
  useState: !!React.useState,
  useEffect: !!React.useEffect,
  useSyncExternalStore: !!React.useSyncExternalStore,
  reactType: typeof React,
  reactKeys: Object.keys(React || {}),
  reactVersion: React?.version || 'unknown'
});

// COMPREHENSIVE MODULE DEPENDENCY TRACING
console.log('🔍 DEPENDENCY ANALYSIS - Before other imports:', {
  timestamp: Date.now(),
  moduleCache: typeof require !== 'undefined' ? Object.keys(require.cache || {}).filter(k => k.includes('react')) : 'require unavailable',
  webpackModules: typeof __webpack_require__ !== 'undefined' ? 'webpack detected' : 'no webpack',
  viteModules: typeof __vite__ !== 'undefined' ? 'vite detected' : 'no vite',
  nodeModules: typeof process !== 'undefined' ? 'node env' : 'browser env'
});

// CRITICAL: Track React state before potentially problematic imports
console.log('🔍 PRE-IMPORT React state check - React Query about to load:', {
  reactUseState: typeof React?.useState,
  reactUseSyncExternalStore: typeof React?.useSyncExternalStore,
  reactOnWindow: typeof window?.React,
  timestamp: Date.now()
});

import { SimpleQueryClient, SimpleQueryProvider } from './hooks/useSimpleFetch.js'

// CRITICAL: Track React state after simple query import
console.log('🔍 POST-IMPORT React state check - After Simple Query loaded:', {
  reactUseState: typeof React?.useState,
  reactUseSyncExternalStore: typeof React?.useSyncExternalStore,
  reactOnWindow: typeof window?.React,
  timestamp: Date.now(),
  SimpleQueryClient: typeof SimpleQueryClient,
  SimpleQueryProvider: typeof SimpleQueryProvider
});
import { BrowserRouter } from 'react-router-dom'
import { ThemeProvider } from '@mui/material/styles'
import CssBaseline from '@mui/material/CssBaseline'

// ENHANCED MUI Theme - proper MUI createTheme implementation
import muiTheme from './theme/muiTheme'

// Enhanced components
import './index.css'
import App from './App'
import ErrorBoundary from './components/ErrorBoundaryTailwind'
import { LoadingProvider } from './components/LoadingStateManager'
import { AuthProvider } from './contexts/AuthContext'
import ApiKeyProvider from './components/ApiKeyProvider'

// Enhanced initialization logging
console.log('🚀 Financial Platform initializing...');
console.log('📍 Location:', window.location.href);
console.log('📄 Document state:', document.readyState);
console.log('🎯 Root element:', !!document.getElementById('root'));

// Log system capabilities
import { getCompatibilityReport } from './utils/browserCompatibility.js';
import { getSystemHealth } from './utils/asyncErrorHandler.js';

console.group('🔍 System Status');
console.log('Browser compatibility:', getCompatibilityReport());
console.log('Error handling health:', getSystemHealth());
console.log('🤖 Automated testing framework: LOADING CONDITIONALLY');
console.groupEnd();

// Initialize automated testing in development after React is ready - DISABLED
// if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
//   console.log('🧪 Development environment detected - loading automated testing...');
//   
//   // Load testing framework after React is fully initialized
//   setTimeout(async () => {
//     try {
//       console.log('🚀 Loading automated testing framework...');
//       const testModule = await import('./utils/automatedTestFramework.js');
//       const automatedTestFramework = testModule.default;
//       
//       console.log('🚀 Running initial automated tests...');
//       const results = await automatedTestFramework.runReactHooksTests();
//       console.log('✅ Initial React hooks tests completed:', results);
//       
//       // Expose to window for manual testing
//       window.automatedTestFramework = automatedTestFramework;
//       
//     } catch (error) {
//       console.error('❌ Failed to load automated testing framework:', error);
//     }
//   }, 3000); // Give more time for React to fully initialize
// }

// Configure Amplify for authentication - but don't let it crash the app
import { configureAmplify } from './config/amplify'

// Configure Amplify safely - continue even if it fails
setTimeout(() => {
  try {
    configureAmplify();
    console.log('✅ Amplify configured successfully');
  } catch (error) {
    console.warn('⚠️ Amplify configuration failed, using fallback auth:', error);
  }
}, 100);

// Create a simple client (no external store dependencies)
const queryClient = new SimpleQueryClient({
  defaultOptions: {
    queries: {
      retry: 3,
      staleTime: 30000,
      cacheTime: 10 * 60 * 1000,
      refetchOnWindowFocus: false,
    },
  },
})

// Enhanced app wrapper with comprehensive error handling and loading states
const AppWithProviders = () => {
  return (
    <ThemeProvider theme={muiTheme}>
      <CssBaseline />
      <LoadingProvider>
        <AuthProvider>
          <ApiKeyProvider>
            <App />
          </ApiKeyProvider>
        </AuthProvider>
      </LoadingProvider>
    </ThemeProvider>
  );
};

try {
  console.log('🔧 Creating React root...');
  const root = ReactDOM.createRoot(document.getElementById('root'));
  
  console.log('🔧 Rendering full dashboard...');
  root.render(
    <ErrorBoundary>
      <BrowserRouter>
        <SimpleQueryProvider client={queryClient}>
          <AppWithProviders />
        </SimpleQueryProvider>
      </BrowserRouter>
    </ErrorBoundary>
  );
  
  console.log('✅ Dashboard rendered successfully!');
} catch (error) {
  console.error('❌ Error rendering dashboard:', error);
  
  // Fallback to basic dashboard
  document.getElementById('root').innerHTML = `
    <div style="padding: 20px; text-align: center; font-family: Arial, sans-serif;">
      <h1 style="color: #d32f2f;">Dashboard Loading Failed</h1>
      <p><strong>Error:</strong> ${error.message}</p>
      <p>Check browser console for details.</p>
      <button onclick="window.location.reload()" style="padding: 10px 20px; background: #1976d2; color: white; border: none; border-radius: 5px; cursor: pointer;">
        Reload Page
      </button>
    </div>
  `;
}