// Test authentication as the frontend would call it
console.log('=== Frontend Authentication Test ===');

const { authenticateToken } = require('./middleware/auth');

// Create mock request with Authorization header like frontend sends
const mockReq = {
  headers: {
    'authorization': 'Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6InRlc3Qta2V5In0.eyJzdWIiOiJ0ZXN0LXVzZXIiLCJlbWFpbCI6InRlc3RAZXhhbXBsZS5jb20iLCJpYXQiOjE2MzIzNjE0MzAsImV4cCI6OTk5OTk5OTk5OX0.fake-signature',
    'content-type': 'application/json',
    'user-agent': 'Mozilla/5.0 (compatible frontend)'
  },
  method: 'GET',
  path: '/api/settings/api-keys'
};

const mockRes = {
  status: (code) => {
    console.log(`❌ Authentication failed with status: ${code}`);
    return {
      json: (data) => {
        console.log('Error response:', JSON.stringify(data, null, 2));
      }
    };
  },
  json: (data) => {
    console.log('✅ Success response (200):', JSON.stringify(data, null, 2));
  }
};

const mockNext = () => {
  console.log('✅ Authentication successful - middleware called next()');
};

console.log('Testing with Authorization Bearer token...');
console.log('Environment check:');
console.log('- NODE_ENV:', process.env.NODE_ENV);
console.log('- ALLOW_DEV_BYPASS:', process.env.ALLOW_DEV_BYPASS);

// Test both development functions
const authModule = require('./middleware/auth');

// Test the middleware
authenticateToken(mockReq, mockRes, mockNext);