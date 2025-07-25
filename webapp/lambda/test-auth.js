// Test authentication logic
console.log('=== Authentication Logic Test ===');

// Test the actual isDevelopment logic
function isDevelopment() {
  return process.env.NODE_ENV === 'development' || process.env.NODE_ENV === 'test' || !process.env.NODE_ENV;
}

function allowDevBypass() {
  return isDevelopment() || process.env.ALLOW_DEV_BYPASS === 'true';
}

console.log('Environment Variables:');
console.log('NODE_ENV:', process.env.NODE_ENV);
console.log('ALLOW_DEV_BYPASS:', process.env.ALLOW_DEV_BYPASS);

console.log('\nFunction Results:');
console.log('isDevelopment():', isDevelopment());
console.log('allowDevBypass():', allowDevBypass());

// Test the actual auth middleware
console.log('\n=== Testing Auth Middleware ===');
try {
  const { authenticateToken } = require('./middleware/auth');
  
  // Create mock request/response
  const mockReq = {
    headers: {},
    method: 'GET',
    path: '/api/settings/api-keys'
  };
  
  const mockRes = {
    status: (code) => {
      console.log('Response status:', code);
      return {
        json: (data) => {
          console.log('Response data:', JSON.stringify(data, null, 2));
        }
      };
    },
    json: (data) => {
      console.log('Response (200):', JSON.stringify(data, null, 2));
    }
  };
  
  const mockNext = () => {
    console.log('Authentication successful - calling next()');
  };
  
  console.log('Testing authentication without token...');
  authenticateToken(mockReq, mockRes, mockNext);
  
} catch (error) {
  console.error('Auth test failed:', error.message);
}