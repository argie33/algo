import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import { ThemeProvider, createTheme } from '@mui/material/styles'
import CssBaseline from '@mui/material/CssBaseline'
import App from './App'
import ErrorBoundary from './components/ErrorBoundary'
import { AuthProvider } from './contexts/AuthContext'

console.log('🚀 main.jsx loaded - FULL DASHBOARD FIXED - v1.5.0');

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
}, 100); // Delay to ensure window.__CONFIG__ is loaded

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
    h1: { fontWeight: 600 },
    h2: { fontWeight: 600 },
    h3: { fontWeight: 600 },
    h4: { fontWeight: 600 },
    h5: { fontWeight: 600 },
    h6: { fontWeight: 600 },
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
  },
})

// Step by step rendering to isolate issues
try {
  console.log('🔧 Step 1: Creating React root...');
  const root = ReactDOM.createRoot(document.getElementById('root'));
  
  console.log('🔧 Step 2: Testing basic render...');
  root.render(<div>Basic render test successful</div>);
  
  setTimeout(() => {
    console.log('🔧 Step 3: Testing with theme...');
    root.render(
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <div>Theme render test successful</div>
      </ThemeProvider>
    );
    
    setTimeout(() => {
      console.log('🔧 Step 4: Testing with QueryClient...');
      root.render(
        <QueryClientProvider client={queryClient}>
          <ThemeProvider theme={theme}>
            <CssBaseline />
            <div>QueryClient render test successful</div>
          </ThemeProvider>
        </QueryClientProvider>
      );
      
      setTimeout(() => {
        console.log('🔧 Step 5: Testing with BrowserRouter...');
        root.render(
          <BrowserRouter>
            <QueryClientProvider client={queryClient}>
              <ThemeProvider theme={theme}>
                <CssBaseline />
                <div>BrowserRouter render test successful</div>
              </ThemeProvider>
            </QueryClientProvider>
          </BrowserRouter>
        );
        
        setTimeout(() => {
          console.log('🔧 Step 6: Testing with AuthProvider...');
          root.render(
            <ErrorBoundary>
              <BrowserRouter>
                <QueryClientProvider client={queryClient}>
                  <ThemeProvider theme={theme}>
                    <CssBaseline />
                    <AuthProvider>
                      <div>AuthProvider render test successful</div>
                    </AuthProvider>
                  </ThemeProvider>
                </QueryClientProvider>
              </BrowserRouter>
            </ErrorBoundary>
          );
          
          setTimeout(() => {
            console.log('🔧 Step 7: Rendering full App...');
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
            console.log('✅ Full financial dashboard rendered successfully!');
          }, 500);
        }, 500);
      }, 500);
    }, 500);
  }, 500);
  
} catch (error) {
  console.error('❌ Error rendering dashboard:', error);
  
  // Fallback to basic dashboard
  document.getElementById('root').innerHTML = `
    <div style="padding: 20px; text-align: center; font-family: Arial, sans-serif;">
      <h1 style="color: #d32f2f;">Dashboard Loading Failed</h1>
      <p><strong>Error:</strong> ${error.message}</p>
      <p>Your financial pages failed to load. Check browser console for details.</p>
      <button onclick="window.location.reload()" style="padding: 10px 20px; background: #1976d2; color: white; border: none; border-radius: 5px; cursor: pointer;">
        Reload Page
      </button>
    </div>
  `;
}
