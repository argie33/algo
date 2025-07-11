console.log('🚀 Step 2: Testing MUI Theme - v1.8.0');

import React from 'react'
import ReactDOM from 'react-dom/client'
import { ThemeProvider, createTheme } from '@mui/material/styles'
import CssBaseline from '@mui/material/CssBaseline'

console.log('✅ React + MUI imports successful');

// Create theme (same as your original)
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
  },
  typography: {
    fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", "Roboto", "Oxygen", "Ubuntu", "Cantarell", "Fira Sans", "Droid Sans", "Helvetica Neue", sans-serif',
  },
})

const root = ReactDOM.createRoot(document.getElementById('root'));

root.render(
  <ThemeProvider theme={theme}>
    <CssBaseline />
    <div style={{ padding: '20px' }}>
      <h1 style={{ color: 'green' }}>✅ React + MUI Theme Working!</h1>
      <p>Material-UI theme is loading successfully.</p>
      <p>Rendered at: {new Date().toLocaleString()}</p>
    </div>
  </ThemeProvider>
);

console.log('✅ MUI Theme render completed');