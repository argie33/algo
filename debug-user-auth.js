#!/usr/bin/env node

/**
 * Debug User Authentication and API Key Issues
 * 
 * This script helps debug the "API key not found" issue by:
 * 1. Checking what user ID is currently being used
 * 2. Looking at what API keys exist in the database
 * 3. Identifying user ID mismatches between sessions
 */

// You can run this in the browser console on the Portfolio page
const debugScript = `
console.log('🔍 DEBUG: User Authentication and API Key Analysis');
console.log('================================================');

// Get current authentication context
const authContext = window.localStorage.getItem('dev_session');
if (authContext) {
  const session = JSON.parse(authContext);
  console.log('📱 Frontend Session (dev_session):');
  console.log('   User ID:', session.user?.userId);
  console.log('   Username:', session.user?.username);
  console.log('   Email:', session.user?.email);
  console.log('   Session expires:', new Date(session.expiresAt));
  console.log('   Access token format:', session.tokens?.accessToken?.substring(0, 30) + '...');
} else {
  console.log('📱 No dev_session found in localStorage');
}

// Check if there are any other auth-related localStorage items
console.log('\\n🔑 All Auth-Related LocalStorage Items:');
for (let i = 0; i < localStorage.length; i++) {
  const key = localStorage.key(i);
  if (key.includes('auth') || key.includes('user') || key.includes('token') || key.includes('cognito')) {
    const value = localStorage.getItem(key);
    try {
      const parsed = JSON.parse(value);
      console.log('   ' + key + ':', typeof parsed === 'object' ? 'Object with keys: ' + Object.keys(parsed).join(', ') : parsed);
    } catch {
      console.log('   ' + key + ':', value.substring(0, 50) + (value.length > 50 ? '...' : ''));
    }
  }
}

// Test what user ID the backend sees
console.log('\\n🔍 Testing Backend Authentication...');
fetch(window.location.origin.replace('3000', '3001') + '/api/settings/api-keys', {
  headers: {
    'Authorization': 'Bearer ' + (JSON.parse(localStorage.getItem('dev_session') || '{}').tokens?.accessToken || 'no-token'),
    'Content-Type': 'application/json'
  }
})
.then(response => response.json())
.then(data => {
  console.log('\\n📊 Backend API Keys Response:');
  console.log('   Success:', data.success);
  console.log('   Total API keys in DB:', data.totalInDatabase || 'unknown');
  console.log('   API keys for this user:', data.apiKeys?.length || 0);
  if (data.apiKeys && data.apiKeys.length > 0) {
    console.log('   API Key Details:');
    data.apiKeys.forEach((key, index) => {
      console.log('     ' + (index + 1) + '. Provider:', key.provider, 'ID:', key.id, 'Sandbox:', key.isSandbox, 'Active:', key.isActive);
    });
  }
  if (data.error) {
    console.log('   Error:', data.error);
    console.log('   Message:', data.message);
  }
})
.catch(error => {
  console.log('\\n❌ Backend API Call Failed:', error.message);
});

// Check what user ID would be used for portfolio import
console.log('\\n💼 Testing Portfolio Import Authentication...');
fetch(window.location.origin.replace('3000', '3001') + '/api/portfolio', {
  headers: {
    'Authorization': 'Bearer ' + (JSON.parse(localStorage.getItem('dev_session') || '{}').tokens?.accessToken || 'no-token'),
    'Content-Type': 'application/json'
  }
})
.then(response => response.json())
.then(data => {
  console.log('\\n📈 Portfolio API Response:');
  console.log('   Success:', data.success);
  console.log('   System:', data.data?.system);
  console.log('   Available endpoints:', data.data?.available_endpoints?.length || 0);
})
.catch(error => {
  console.log('\\n❌ Portfolio API Call Failed:', error.message);
});

console.log('\\n🎯 Next Steps:');
console.log('1. Check if the User ID shown above matches between frontend and backend');
console.log('2. Look for API keys in the database for the correct user ID');
console.log('3. If user IDs mismatch, you may need to re-save your API key');
console.log('4. If using real Cognito, make sure you\\'re consistently logged in');
`;

console.log('🔧 DEBUGGING INSTRUCTIONS');
console.log('========================');
console.log('');
console.log('To debug the "API key not found" issue:');
console.log('');
console.log('1. Open your browser to the Portfolio page');
console.log('2. Open Developer Tools (F12)');
console.log('3. Go to the Console tab');
console.log('4. Copy and paste the following code:');
console.log('');
console.log('```javascript');
console.log(debugScript);
console.log('```');
console.log('');
console.log('5. Press Enter to run the debug script');
console.log('6. Look for user ID mismatches in the output');
console.log('');
console.log('📋 Common Issues:');
console.log('- Frontend user ID differs from backend user ID');
console.log('- API key was saved with old session, now using new session');
console.log('- Switched between development auth and Cognito auth');
console.log('- API key was saved but for different provider/user combination');
console.log('');
console.log('🔧 Quick Fixes:');
console.log('- Delete API key in Settings and re-add it');
console.log('- Clear localStorage and log in again');
console.log('- Check that you\\'re using consistent authentication method');

// Export the debug script for easy copying
module.exports = { debugScript };