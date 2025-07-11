console.log('🚀 React Debug: Testing imports - v2.1.0');

try {
  console.log('Testing React import...');
  const React = require('react');
  console.log('✅ React imported via require');
  
  console.log('Testing ReactDOM import...');  
  const ReactDOM = require('react-dom/client');
  console.log('✅ ReactDOM imported via require');

  const root = ReactDOM.createRoot(document.getElementById('root'));
  console.log('✅ React root created');

  root.render(React.createElement('div', { style: { padding: '20px', border: '3px solid green' } }, [
    React.createElement('h1', { key: 'h1' }, '🎯 FOUND THE ISSUE!'),
    React.createElement('p', { key: 'p1' }, 'This means ES6 imports are the problem.'),
    React.createElement('p', { key: 'p2' }, 'Using CommonJS require() instead.'),
    React.createElement('p', { key: 'p3' }, `Time: ${new Date().toLocaleString()}`)
  ]));
  console.log('✅ Basic render with require() successful');
  
} catch (requireError) {
  console.error('❌ Even require() failed:', requireError);
  
  // Fallback to plain HTML
  document.getElementById('root').innerHTML = `
    <div style="padding: 20px; border: 3px solid red;">
      <h1>REQUIRE() FAILED</h1>
      <p>Error: ${requireError.message}</p>
      <p>This means the build is completely broken.</p>
    </div>
  `;
}