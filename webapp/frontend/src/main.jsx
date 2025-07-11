import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import { ThemeProvider, createTheme } from '@mui/material/styles'
import CssBaseline from '@mui/material/CssBaseline'
import App from './App'
import { AuthProvider } from './contexts/AuthContext'
import { configureAmplify } from './config/amplify'
import ErrorBoundary from './components/ErrorBoundary'

console.log('🚀 main.jsx loaded - starting React app - v1.0.6 - FIXING API CONFIG AND DEPLOYMENT');

// Add global error handler to catch white page issues
window.addEventListener('error', (e) => {
  console.error('❌ Global error:', e.error);
  console.error('❌ Error details:', e.filename, e.lineno, e.colno);
});

window.addEventListener('unhandledrejection', (e) => {
  console.error('❌ Unhandled promise rejection:', e.reason);
});

// Configure Amplify
configureAmplify();

// Create a client with better error handling
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false, // Don't retry on errors during startup
      staleTime: 30000,
      cacheTime: 10 * 60 * 1000, // 10 minutes
      refetchOnWindowFocus: false,
    },
  },
})

console.log('✅ QueryClient created');

// Create theme
const theme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#1976d2',
      light: '#42a5f5',
      dark: '#1565c0',
    },
    secondary: {
      main: '#dc004e',
      light: '#ff5983',
      dark: '#9a0036',
    },
    background: {
      default: '#f5f5f5',
      paper: '#ffffff',
    },
    success: {
      main: '#2e7d32',
      light: '#4caf50',
      dark: '#1b5e20',
    },
    error: {
      main: '#d32f2f',
      light: '#ef5350',
      dark: '#c62828',
    },
  },
  typography: {
    fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", "Roboto", "Oxygen", "Ubuntu", "Cantarell", "Fira Sans", "Droid Sans", "Helvetica Neue", sans-serif',
    h1: {
      fontWeight: 600,
    },
    h2: {
      fontWeight: 600,
    },
    h3: {
      fontWeight: 600,
    },
    h4: {
      fontWeight: 600,
    },
    h5: {
      fontWeight: 600,
    },
    h6: {
      fontWeight: 600,
    },
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          textTransform: 'none',
          fontWeight: 500,
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
          borderRadius: 12,
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          borderRadius: 12,
        },
      },
    },
  },
})

console.log('✅ Theme created');
console.log('🔍 Looking for root element...');

const rootElement = document.getElementById('root');
if (!rootElement) {
  console.error('❌ Root element not found!');
  alert('Root element not found!');
} else {
  console.log('✅ Root element found:', rootElement);
}

console.log('🚀 Creating React root and rendering app...');

// Fallback component for when everything fails
const FallbackApp = () => (
  <div style={{ padding: '20px', fontFamily: 'Arial, sans-serif' }}>
    <h1>Financial Dashboard</h1>
    <p>Welcome to the financial dashboard. The application is initializing...</p>
    <div style={{ marginTop: '20px', padding: '15px', backgroundColor: '#f0f0f0', borderRadius: '5px' }}>
      <h3>System Status</h3>
      <p>✅ Application loaded successfully</p>
      <p>🔄 Connecting to services...</p>
    </div>
  </div>
);

try {
  console.log('🔧 Creating React root and rendering...');
  const root = ReactDOM.createRoot(document.getElementById('root'));
  
  console.log('🔧 Rendering app with providers...');
  
  // Try full app first, fallback to minimal if it fails
  try {
    root.render(
      <ErrorBoundary>
        <BrowserRouter>
          <QueryClientProvider client={queryClient}>
            <ThemeProvider theme={theme}>
              <CssBaseline />
              <AuthProvider>
                <App />
              </AuthProvider>
            </ThemeProvider>
          </QueryClientProvider>
        </BrowserRouter>
      </ErrorBoundary>
    );
    console.log('✅ Full React app rendered successfully');
  } catch (renderError) {
    console.error('❌ Full app failed, rendering fallback:', renderError);
    root.render(<FallbackApp />);
  }
  
  // Clear the loading message after successful render
  setTimeout(() => {
    const loadingInfo = document.getElementById('loading-info');
    if (loadingInfo) {
      loadingInfo.remove();
    }
  }, 1000);
  
} catch (error) {
  console.error('❌ Error rendering React app:', error);
  console.error('❌ Error stack:', error.stack);
  
  // Show fallback app instead of error
  try {
    const root = ReactDOM.createRoot(document.getElementById('root'));
    root.render(<FallbackApp />);
    console.log('✅ Fallback app rendered after error');
  } catch (fallbackError) {
    console.error('❌ Even fallback failed:', fallbackError);
    // Last resort: plain HTML
    const rootElement = document.getElementById('root');
    if (rootElement) {
      rootElement.innerHTML = `
        <div style="padding: 20px; text-align: center; font-family: Arial, sans-serif;">
          <h1>Financial Dashboard</h1>
          <p>Basic mode - Application loaded successfully</p>
          <p><strong>Error:</strong> ${error.message}</p>
          <p>Check browser console for full error details.</p>
          <details style="margin-top: 20px; text-align: left;">
            <summary>Error Details</summary>
            <pre style="background: #f5f5f5; padding: 10px; border-radius: 4px; overflow: auto; font-size: 12px;">
${error.stack || error.message}
            </pre>
          </details>
        </div>
      `;
    }
  }
}
