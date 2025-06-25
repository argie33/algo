const { app } = require('./index');

// Test the health endpoint directly
const testHealth = async () => {
  const req = {
    method: 'GET',
    path: '/health',
    query: { quick: 'true' },
    headers: {}
  };
  
  const res = {
    status: (code) => {
      console.log('Status:', code);
      return res;
    },
    json: (data) => {
      console.log('Response:', JSON.stringify(data, null, 2));
      return res;
    }
  };
  
  try {
    await app._router.handle(req, res, () => {});
  } catch (error) {
    console.error('Error:', error);
  }
};

testHealth(); 