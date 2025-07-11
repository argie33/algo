console.log('🚀 MINIMAL React Test - v1.7.0');

import React from 'react'
import ReactDOM from 'react-dom/client'

console.log('✅ React imports successful');

// Most basic React test possible
const root = ReactDOM.createRoot(document.getElementById('root'));
console.log('✅ React root created');

root.render(
  React.createElement('div', { style: { padding: '20px', fontFamily: 'Arial' } }, [
    React.createElement('h1', { key: 'title', style: { color: 'green' } }, '✅ React is Working!'),
    React.createElement('p', { key: 'msg' }, 'If you see this, React is rendering successfully.'),
    React.createElement('p', { key: 'time' }, `Rendered at: ${new Date().toLocaleString()}`)
  ])
);

console.log('✅ Basic React render completed');