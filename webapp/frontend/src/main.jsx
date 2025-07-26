import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import { ThemeProvider } from '@mui/material/styles'
import CssBaseline from '@mui/material/CssBaseline'

import App from './App'
import { queryClient } from './lib/queryClient'
import muiTheme from './theme/muiTheme'
import { AuthProvider } from './contexts/AuthContext'
import { ApiKeyProvider } from './components/ApiKeyProvider'

// Import styles
import './index.css'
import './mobile-responsive.css'

// Configure Amplify for authentication
import { configureAmplify } from './config/amplify'

// Configure Amplify safely
try {
  configureAmplify();
} catch (error) {
  console.warn('⚠️ Amplify configuration failed, using fallback auth:', error);
}

const root = ReactDOM.createRoot(document.getElementById('root'))

root.render(
  <QueryClientProvider client={queryClient}>
    <BrowserRouter>
      <ThemeProvider theme={muiTheme}>
        <CssBaseline />
        <AuthProvider>
          <ApiKeyProvider>
            <App />
          </ApiKeyProvider>
        </AuthProvider>
      </ThemeProvider>
    </BrowserRouter>
    <ReactQueryDevtools initialIsOpen={false} />
  </QueryClientProvider>
)