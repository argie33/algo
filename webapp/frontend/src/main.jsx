console.log('🚀 Step 2a: Testing MUI step by step - v1.8.2');

import React from 'react'
import ReactDOM from 'react-dom/client'

console.log('✅ React imports successful');

const root = ReactDOM.createRoot(document.getElementById('root'));

// Test 1: Basic render first
root.render(
  <div style={{ padding: '20px' }}>
    <h1 style={{ color: 'blue' }}>Step 1: Basic React ✅</h1>
    <p>About to test MUI imports...</p>
  </div>
);

// Test 2: Try MUI imports after a delay
setTimeout(async () => {
  try {
    console.log('Testing MUI styles import...');
    const stylesModule = await import('@mui/material/styles');
    console.log('✅ MUI styles loaded:', Object.keys(stylesModule));
    
    const { ThemeProvider, createTheme } = stylesModule;
    
    console.log('Testing CssBaseline import...');
    const CssBaselineModule = await import('@mui/material/CssBaseline');
    console.log('✅ CssBaseline loaded');
    
    const CssBaseline = CssBaselineModule.default;
    
    // Create simple theme
    const theme = createTheme({
      palette: { mode: 'light' }
    });
    
    console.log('✅ Theme created, rendering with MUI...');
    
    root.render(
      React.createElement(ThemeProvider, { theme }, [
        React.createElement(CssBaseline, { key: 'baseline' }),
        React.createElement('div', { key: 'content', style: { padding: '20px' } }, [
          React.createElement('h1', { key: 'title', style: { color: 'green' } }, 'Step 2: MUI Working! ✅'),
          React.createElement('p', { key: 'msg' }, 'Material-UI loaded successfully'),
          React.createElement('p', { key: 'time' }, `Time: ${new Date().toLocaleString()}`)
        ])
      ])
    );
    
  } catch (error) {
    console.error('❌ MUI Error:', error);
    root.render(
      React.createElement('div', { style: { padding: '20px' } }, [
        React.createElement('h1', { key: 'title', style: { color: 'red' } }, 'MUI Import Failed'),
        React.createElement('p', { key: 'error' }, `Error: ${error.message}`),
        React.createElement('pre', { key: 'stack' }, error.stack || 'No stack trace')
      ])
    );
  }
}, 1000);