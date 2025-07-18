// Initialize essential utilities FIRST
import './utils/browserCompatibility.js'
import asyncErrorHandler from './utils/asyncErrorHandler.js'
import memoryLeakPrevention from './utils/memoryLeakPrevention.js'
import performanceMonitor from './utils/performanceMonitor.js'
import debugInit from './utils/debugInit.js'
import automatedTestFramework from './utils/automatedTestFramework.js'

import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import { ThemeProvider } from '@mui/material/styles'
import CssBaseline from '@mui/material/CssBaseline'

// MUI Theme to prevent createPalette errors
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
console.log('🤖 Automated testing framework:', automatedTestFramework ? 'ACTIVE' : 'INACTIVE');
console.groupEnd();

// Initialize automated testing in development
if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
  console.log('🧪 Development environment detected - automated testing enabled');
  
  // Run initial automated tests after app loads
  setTimeout(() => {
    console.log('🚀 Running initial automated tests...');
    automatedTestFramework.runReactHooksTests().then(results => {
      console.log('✅ Initial React hooks tests completed:', results);
    }).catch(error => {
      console.error('❌ Initial React hooks tests failed:', error);
    });
  }, 2000);
}

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

// Create a client
const queryClient = new QueryClient({
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
        <QueryClientProvider client={queryClient}>
          <AppWithProviders />
        </QueryClientProvider>
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