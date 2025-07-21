#!/usr/bin/env node

/**
 * NETWORK MONITOR - Find the hidden shim file request
 */

const http = require('http');
const url = require('url');

// Start a proxy server to intercept ALL requests
const server = http.createServer((req, res) => {
  const requestUrl = req.url;
  
  // Log EVERY request
  console.log(`📡 REQUEST: ${req.method} ${requestUrl}`);
  
  // Check if this is the problematic shim file request
  if (requestUrl.includes('use-sync-external-store-shim')) {
    console.log('🚨 FOUND SHIM REQUEST!');
    console.log(`   URL: ${requestUrl}`);
    console.log(`   Method: ${req.method}`);
    console.log(`   Headers:`, req.headers);
    
    // Return a custom response to prevent the error
    res.writeHead(200, {'Content-Type': 'application/javascript'});
    res.end(`
// INTERCEPTED SHIM FILE - SAFE VERSION
console.log('🔧 Custom shim file loaded - preventing useState error');

// Export a safe implementation
if (typeof module !== 'undefined' && module.exports) {
  module.exports = function useSyncExternalStoreShim(subscribe, getSnapshot, getServerSnapshot) {
    console.log('🔧 useSyncExternalStoreShim called with custom implementation');
    if (typeof window !== 'undefined' && window.React && window.React.useSyncExternalStore) {
      return window.React.useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
    }
    
    // Fallback implementation
    const [state, setState] = window.React.useState(getSnapshot);
    window.React.useEffect(() => {
      const unsubscribe = subscribe(() => {
        setState(getSnapshot());
      });
      return unsubscribe;
    }, [subscribe, getSnapshot]);
    
    return state;
  };
}
`);
    return;
  }
  
  // For all other requests, proxy to the original server
  const options = {
    hostname: 'localhost',
    port: 8080,
    path: requestUrl,
    method: req.method,
    headers: req.headers
  };
  
  const proxyReq = http.request(options, (proxyRes) => {
    res.writeHead(proxyRes.statusCode, proxyRes.headers);
    proxyRes.pipe(res);
  });
  
  proxyReq.on('error', (err) => {
    console.error('❌ Proxy error:', err.message);
    res.writeHead(500);
    res.end('Proxy Error');
  });
  
  req.pipe(proxyReq);
});

server.listen(8081, () => {
  console.log('🔍 NETWORK MONITOR PROXY RUNNING');
  console.log('===============================');
  console.log('🌐 Proxy server: http://localhost:8081');
  console.log('🎯 Target server: http://localhost:8080');
  console.log('📊 Monitoring ALL network requests...');
  console.log('🚨 Will intercept any shim file requests');
  console.log('');
  console.log('✅ Open http://localhost:8081 in your browser to test');
  console.log('⏹️  Press Ctrl+C to stop monitoring');
});

process.on('SIGINT', () => {
  console.log('\n📊 Network monitoring stopped');
  process.exit(0);
});