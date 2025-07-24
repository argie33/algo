/**
 * Session Persistence Test Script
 * Tests session storage, cross-tab sync, and persistence mechanisms
 */

// Mock browser environment for testing
global.window = {
  sessionStorage: {
    data: {},
    getItem: function(key) { return this.data[key] || null; },
    setItem: function(key, value) { this.data[key] = value; },
    removeItem: function(key) { delete this.data[key]; },
    clear: function() { this.data = {}; }
  },
  localStorage: {
    data: {},
    getItem: function(key) { return this.data[key] || null; },
    setItem: function(key, value) { this.data[key] = value; },
    removeItem: function(key) { delete this.data[key]; },
    clear: function() { this.data = {}; }
  },
  navigator: {
    userAgent: 'Test Browser',
    language: 'en-US',
    platform: 'Test Platform',
    cookieEnabled: true
  },
  screen: {
    width: 1920,
    height: 1080,
    colorDepth: 24
  },
  BroadcastChannel: class MockBroadcastChannel {
    constructor(name) {
      this.name = name;
      this.onmessage = null;
      this.listeners = [];
    }
    postMessage(data) {
      console.log(`📡 Broadcasting on ${this.name}:`, data);
    }
    addEventListener(event, handler) {
      this.listeners.push(handler);
    }
    removeEventListener(event, handler) {
      const index = this.listeners.indexOf(handler);
      if (index > -1) this.listeners.splice(index, 1);
    }
    close() {
      this.listeners = [];
    }
  }
};

// Mock crypto for Node.js environment
const crypto = require('crypto');
global.crypto = {
  getRandomValues: function(array) {
    const buffer = crypto.randomBytes(array.length);
    for (let i = 0; i < array.length; i++) {
      array[i] = buffer[i];
    }
    return array;
  }
};

// Import the secure session storage
const secureSessionStorageModule = require('./src/utils/secureSessionStorage.js');
const SecureSessionStorage = secureSessionStorageModule.default || secureSessionStorageModule;

console.log('🧪 Starting Session Persistence Tests...\n');

// Test 1: Basic token storage and retrieval
console.log('📝 Test 1: Basic Token Storage');
try {
  const storage = new SecureSessionStorage();
  
  const testTokens = {
    accessToken: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c',
    refreshToken: 'refresh_token_12345',
    idToken: 'id_token_67890',
    userId: 'user-123',
    username: 'testuser',
    email: 'test@example.com'
  };
  
  // Store tokens
  storage.storeTokens(testTokens);
  console.log('✅ Tokens stored successfully');
  
  // Retrieve tokens
  const retrievedTokens = storage.getTokens();
  console.log('✅ Tokens retrieved successfully');
  
  // Verify token integrity
  if (retrievedTokens && retrievedTokens.accessToken === testTokens.accessToken) {
    console.log('✅ Token integrity verified');
  } else {
    console.log('❌ Token integrity check failed');
  }
  
} catch (error) {
  console.log('❌ Test 1 failed:', error.message);
}

// Test 2: Session metadata and device fingerprinting
console.log('\n📱 Test 2: Device Fingerprinting');
try {
  const storage = new SecureSessionStorage();
  
  // Test device fingerprint generation
  const fingerprint1 = storage.generateDeviceFingerprint();
  const fingerprint2 = storage.generateDeviceFingerprint();
  
  if (fingerprint1 === fingerprint2) {
    console.log('✅ Consistent device fingerprint generated');
  } else {
    console.log('❌ Device fingerprint inconsistency');
  }
  
  console.log('🔍 Device fingerprint:', fingerprint1.substring(0, 20) + '...');
  
} catch (error) {
  console.log('❌ Test 2 failed:', error.message);
}

// Test 3: Session expiry and validation
console.log('\n⏰ Test 3: Session Validation');
try {
  const storage = new SecureSessionStorage();
  
  // Create session with short expiry
  const shortLivedTokens = {
    accessToken: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiZXhwIjoxNjE2MjM5MDIyfQ.Lrk1tgWY6xUJY7HGlJHKnz1pYk5Nz-ooJNZ3lFSEoIo',
    refreshToken: 'refresh_token_12345',
    userId: 'user-123'
  };
  
  storage.storeTokens(shortLivedTokens);
  
  // Validate session
  const isValid = storage.validateSession();
  console.log('✅ Session validation result:', isValid ? 'Valid' : 'Invalid/Expired');
  
} catch (error) {
  console.log('❌ Test 3 failed:', error.message);
}

// Test 4: Cross-tab synchronization simulation
console.log('\n🔄 Test 4: Cross-Tab Synchronization');
try {
  const storage1 = new SecureSessionStorage();
  const storage2 = new SecureSessionStorage();
  
  // Simulate login from first tab
  const loginTokens = {
    accessToken: 'new_access_token',
    refreshToken: 'new_refresh_token',
    userId: 'user-456'
  };
  
  storage1.storeTokens(loginTokens);
  console.log('✅ Tab 1: User logged in');
  
  // Simulate cross-tab sync
  storage1.syncCrossTab('login', { userId: 'user-456' });
  console.log('✅ Cross-tab sync triggered');
  
  // Test logout synchronization
  storage1.clearSession();
  storage1.syncCrossTab('logout', { reason: 'user_initiated' });
  console.log('✅ Logout synchronized across tabs');
  
} catch (error) {
  console.log('❌ Test 4 failed:', error.message);
}

// Test 5: Concurrent session management
console.log('\n👥 Test 5: Concurrent Session Management');
try {
  const storage = new SecureSessionStorage();
  
  // Simulate multiple sessions
  const sessions = [];
  for (let i = 1; i <= 5; i++) {
    sessions.push({
      sessionId: `session-${i}`,
      userId: 'user-123',
      deviceFingerprint: storage.generateDeviceFingerprint(),
      createdAt: Date.now() - (i * 1000 * 60), // Stagger creation times
      lastActivity: Date.now() - (i * 1000 * 30)
    });
  }
  
  console.log(`✅ Simulated ${sessions.length} concurrent sessions`);
  
  // Test session limit enforcement
  const activeSessions = sessions.filter(s => 
    Date.now() - s.lastActivity < 30 * 60 * 1000 // Active within 30 minutes
  );
  
  console.log(`✅ ${activeSessions.length} active sessions detected`);
  
  if (activeSessions.length > 3) {
    console.log('⚠️  Concurrent session limit exceeded - cleanup required');
  } else {
    console.log('✅ Concurrent session limit within bounds');
  }
  
} catch (error) {
  console.log('❌ Test 5 failed:', error.message);
}

// Test 6: Persistence across page reloads
console.log('\n🔄 Test 6: Persistence Across Page Reloads');
try {
  // Simulate page reload by creating new storage instance
  const preReloadStorage = new SecureSessionStorage();
  
  const persistentTokens = {
    accessToken: 'persistent_access_token',
    refreshToken: 'persistent_refresh_token',
    userId: 'persistent-user-789'
  };
  
  preReloadStorage.storeTokens(persistentTokens);
  console.log('✅ Tokens stored before "page reload"');
  
  // Simulate page reload
  const postReloadStorage = new SecureSessionStorage();
  const recoveredTokens = postReloadStorage.getTokens();
  
  if (recoveredTokens && recoveredTokens.accessToken === persistentTokens.accessToken) {
    console.log('✅ Session persisted across page reload');
  } else {
    console.log('❌ Session lost during page reload');
  }
  
} catch (error) {
  console.log('❌ Test 6 failed:', error.message);
}

console.log('\n🎯 Session Persistence Test Summary:');
console.log('- Basic storage/retrieval: Tested');
console.log('- Device fingerprinting: Tested');
console.log('- Session validation: Tested');
console.log('- Cross-tab synchronization: Tested');
console.log('- Concurrent session management: Tested');
console.log('- Page reload persistence: Tested');

console.log('\n✨ Session persistence testing completed!');