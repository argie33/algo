/**
 * Simple WebSocket Connection Test
 * Quick verification that the WebSocket infrastructure is working
 */

import liveDataService from './src/services/liveDataService.js';

console.log('🧪 Testing WebSocket Connection to AWS Infrastructure...');
console.log('📡 Endpoint:', liveDataService.config.wsUrl);

// Mock localStorage for authentication
global.localStorage = {
  getItem: (key) => {
    if (key === 'accessToken' || key === 'authToken') {
      // Mock JWT token
      return 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0LXVzZXItMTIzIiwidXNlcklkIjoidGVzdC11c2VyLTEyMyIsImV4cCI6OTk5OTk5OTk5OX0.signature';
    }
    return null;
  },
  setItem: () => {},
  clear: () => {}
};

global.atob = (str) => {
  return JSON.stringify({ sub: 'test-user-123', userId: 'test-user-123', exp: 9999999999 });
};

// Set up event listeners
liveDataService.on('connecting', (details) => {
  console.log('🔄 Connecting...', details);
});

liveDataService.on('connected', (details) => {
  console.log('✅ Connected!', details);
  
  // Test subscription
  console.log('📊 Testing market data subscription...');
  liveDataService.subscribe(['AAPL', 'MSFT']);
});

liveDataService.on('subscribed', (data) => {
  console.log('✅ Subscription confirmed:', data);
});

liveDataService.on('marketData', (data) => {
  console.log('📈 Market data received:', data);
});

liveDataService.on('error', (error) => {
  console.error('❌ WebSocket Error:', error);
});

liveDataService.on('configurationError', (error) => {
  console.error('❌ Configuration Error:', error);
});

liveDataService.on('authenticationError', (error) => {
  console.error('❌ Authentication Error:', error);
});

liveDataService.on('disconnected', (details) => {
  console.log('🔴 Disconnected:', details);
});

// Start connection test
async function testConnection() {
  try {
    console.log('🚀 Starting connection test...');
    await liveDataService.connect('test-user-123');
    
    // Wait for potential connection
    setTimeout(() => {
      const status = liveDataService.getConnectionStatus();
      const metrics = liveDataService.getMetrics();
      const health = liveDataService.healthCheck();
      
      console.log('\n📊 Connection Results:');
      console.log('Status:', status);
      console.log('Connected:', liveDataService.isConnected());
      console.log('Metrics:', metrics);
      console.log('Health:', health);
      
      if (liveDataService.isConnected()) {
        console.log('\n✅ SUCCESS: WebSocket infrastructure is working!');
        
        // Test ping
        liveDataService.sendMessage({ action: 'ping', timestamp: Date.now() });
      } else {
        console.log('\n⚠️  Connection not established - check AWS infrastructure');
      }
      
      // Cleanup after test
      setTimeout(() => {
        liveDataService.cleanup();
        console.log('🧹 Test completed and cleaned up');
        process.exit(0);
      }, 5000);
    }, 10000);
    
  } catch (error) {
    console.error('❌ Test failed:', error);
    process.exit(1);
  }
}

testConnection();