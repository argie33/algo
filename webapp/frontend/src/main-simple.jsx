import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { ThemeProvider, createTheme } from '@mui/material/styles'
import CssBaseline from '@mui/material/CssBaseline'
import App from './App-simple'

console.log('🚀 SIMPLE VERSION - No Amplify, No Auth, No Complex Stuff');

// Simple theme
const theme = createTheme({
  palette: {
    mode: 'light',
    primary: { main: '#1976d2' },
    secondary: { main: '#dc004e' },
  },
});

// Simple App without all the complex providers
const SimpleApp = () => (
  <BrowserRouter>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <App />
    </ThemeProvider>
  </BrowserRouter>
);

try {
  const root = ReactDOM.createRoot(document.getElementById('root'));
  root.render(<SimpleApp />);
  console.log('✅ Simple app rendered successfully');
} catch (error) {
  console.error('❌ Simple app failed:', error);
}