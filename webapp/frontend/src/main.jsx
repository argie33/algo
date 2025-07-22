import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { ThemeProvider } from '@mui/material/styles'
import CssBaseline from '@mui/material/CssBaseline'

// Import theme - COMPLEX IMPLEMENTATION
import muiTheme from './theme/muiTheme'

// Import core components
import './index.css'
import './mobile-responsive.css'
import App from './App'
import EnhancedAsyncErrorBoundary from './components/EnhancedAsyncErrorBoundary'
import { LoadingProvider } from './components/LoadingStateManager'
import { AuthProvider } from './contexts/AuthContext'
import ApiKeyProvider from './components/ApiKeyProvider'
import { SimpleQueryClient, SimpleQueryProvider } from './hooks/useSimpleFetch.js'

// Configure Amplify for authentication
import { configureAmplify } from './config/amplify'

// Configure Amplify safely
try {
  configureAmplify();
} catch (error) {
  console.warn('⚠️ Amplify configuration failed, using fallback auth:', error);
}

// Create query client
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

// Main app component - COMPLEX IMPLEMENTATION
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

// Render application - COMPLEX ERROR BOUNDARY
const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <EnhancedAsyncErrorBoundary>
    <BrowserRouter
      future={{
        v7_startTransition: true,
        v7_relativeSplatPath: true
      }}
    >
      <SimpleQueryProvider client={queryClient}>
        <AppWithProviders />
      </SimpleQueryProvider>
    </BrowserRouter>
  </EnhancedAsyncErrorBoundary>
);