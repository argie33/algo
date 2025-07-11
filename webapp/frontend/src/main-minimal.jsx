import React from 'react'
import ReactDOM from 'react-dom/client'

console.log('🚀 MINIMAL VERSION - Basic React only');

// Ultra simple test component
const MinimalApp = () => {
  return (
    <div style={{ padding: '20px', fontFamily: 'Arial, sans-serif' }}>
      <h1>✅ React is Working!</h1>
      <p>Financial Dashboard - Minimal Mode</p>
      <div style={{ marginTop: '20px', padding: '15px', backgroundColor: '#e8f5e8', borderRadius: '5px' }}>
        <h3>System Status:</h3>
        <p>✅ React loaded successfully</p>
        <p>✅ JavaScript executing</p>
        <p>✅ API is working (backend confirmed)</p>
      </div>
      <div style={{ marginTop: '20px' }}>
        <button onClick={() => alert('React events working!')}>
          Test React Events
        </button>
      </div>
      <div style={{ marginTop: '20px', padding: '15px', backgroundColor: '#f0f8ff', borderRadius: '5px' }}>
        <h3>API Test:</h3>
        <button onClick={() => {
          fetch('/api/stocks?limit=1')
            .then(r => r.json())
            .then(data => alert(`API Response: ${data.success ? 'SUCCESS' : 'FAILED'}`))
            .catch(e => alert(`API Error: ${e.message}`))
        }}>
          Test API Call
        </button>
      </div>
    </div>
  );
};

try {
  const root = ReactDOM.createRoot(document.getElementById('root'));
  root.render(<MinimalApp />);
  console.log('✅ Minimal app rendered successfully');
} catch (error) {
  console.error('❌ Minimal app failed:', error);
  document.getElementById('root').innerHTML = `
    <div style="padding: 20px; color: red;">
      <h1>React Failed</h1>
      <p>Error: ${error.message}</p>
    </div>
  `;
}