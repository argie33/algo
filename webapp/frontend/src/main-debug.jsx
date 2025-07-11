import React from 'react'
import ReactDOM from 'react-dom/client'

console.log('🚀 DEBUG VERSION - main-debug.jsx loaded');

// Simple test component
const DebugApp = () => {
  return (
    <div style={{ padding: '20px', fontFamily: 'Arial, sans-serif' }}>
      <h1>🔧 DEBUG MODE</h1>
      <p>✅ React is working</p>
      <p>✅ JavaScript is working</p>
      <p>✅ DOM is accessible</p>
      
      <div style={{ marginTop: '20px', padding: '15px', backgroundColor: '#e8f5e8', borderRadius: '5px' }}>
        <h3>Environment Check:</h3>
        <p><strong>Location:</strong> {window.location.href}</p>
        <p><strong>Config Available:</strong> {window.__CONFIG__ ? 'YES' : 'NO'}</p>
        <p><strong>API URL:</strong> {window.__CONFIG__?.API_URL || 'NOT SET'}</p>
      </div>
      
      <div style={{ marginTop: '20px', padding: '15px', backgroundColor: '#f0f8ff', borderRadius: '5px' }}>
        <h3>Next Steps:</h3>
        <p>If you see this, React is working. The issue is likely in:</p>
        <ul>
          <li>Authentication/Amplify setup</li>
          <li>Component imports</li>
          <li>Provider configurations</li>
        </ul>
      </div>
    </div>
  );
};

console.log('🔧 Creating React root and rendering debug app...');

try {
  const root = ReactDOM.createRoot(document.getElementById('root'));
  root.render(<DebugApp />);
  console.log('✅ Debug app rendered successfully');
} catch (error) {
  console.error('❌ Debug app failed:', error);
  document.getElementById('root').innerHTML = `
    <div style="padding: 20px; color: red;">
      <h1>Critical Error</h1>
      <p>Even the debug app failed: ${error.message}</p>
    </div>
  `;
}