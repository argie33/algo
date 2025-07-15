import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import { ThemeProvider as MuiThemeProvider } from '@mui/material/styles'
import CssBaseline from '@mui/material/CssBaseline'
import App from './App'
import ErrorBoundary from './components/ErrorBoundary'
import { AuthProvider } from './contexts/AuthContext'
import { ThemeProvider, useTheme } from './contexts/ThemeContext'
import ApiKeyProvider from './components/ApiKeyProvider'

console.log('🚀 main.jsx loaded - RESTORED ORIGINAL');
console.log('Window location:', window.location.href);
console.log('Document ready state:', document.readyState);
console.log('Root element exists:', !!document.getElementById('root'));

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

// Create a component that uses the theme from context
const AppWithTheme = () => {
  const { theme } = useTheme();
  
  return (
    <MuiThemeProvider theme={theme}>
      <CssBaseline />
      <AuthProvider>
        <ApiKeyProvider>
          <App />
        </ApiKeyProvider>
      </AuthProvider>
    </MuiThemeProvider>
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
          <ThemeProvider>
            <AppWithTheme />
          </ThemeProvider>
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