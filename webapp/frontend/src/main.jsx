console.log('🚀 ULTRA BASIC TEST - No JSX - v1.9.0');

// Test if the issue is JSX compilation
try {
  console.log('Step 1: Testing imports...');
  
  const React = window.React || (await import('react'));
  console.log('✅ React imported');
  
  const ReactDOM = window.ReactDOM || (await import('react-dom/client'));
  console.log('✅ ReactDOM imported');
  
  console.log('Step 2: Testing DOM access...');
  const rootElement = document.getElementById('root');
  console.log('✅ Root element found:', rootElement);
  
  console.log('Step 3: Testing React root creation...');
  const root = ReactDOM.createRoot(rootElement);
  console.log('✅ React root created');
  
  console.log('Step 4: Testing basic render with createElement...');
  
  // Use React.createElement instead of JSX
  const element = React.createElement('div', 
    { style: { padding: '20px', fontFamily: 'Arial', border: '2px solid green' } },
    [
      React.createElement('h1', { key: 'h1' }, '🎉 ULTRA BASIC REACT WORKS!'),
      React.createElement('p', { key: 'p1' }, 'No JSX, pure createElement'),
      React.createElement('p', { key: 'p2' }, 'If you see this, React core is working'),
      React.createElement('p', { key: 'p3' }, `Timestamp: ${Date.now()}`)
    ]
  );
  
  root.render(element);
  console.log('✅ RENDER SUCCESSFUL!');
  
} catch (error) {
  console.error('❌ CRITICAL ERROR:', error);
  
  // Fallback to vanilla JS
  const rootEl = document.getElementById('root');
  if (rootEl) {
    rootEl.innerHTML = `
      <div style="padding: 20px; border: 2px solid red; font-family: Arial;">
        <h1 style="color: red;">CRITICAL ERROR DETECTED</h1>
        <p><strong>Error:</strong> ${error.message}</p>
        <p><strong>Type:</strong> ${error.name}</p>
        <pre style="background: #f5f5f5; padding: 10px; overflow: auto;">
${error.stack || 'No stack trace available'}
        </pre>
        <p><em>This error prevents React from loading at all.</em></p>
      </div>
    `;
  }
}