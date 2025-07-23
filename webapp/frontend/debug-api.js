// Debug script to test API authentication
console.log('=== API Debug Information ===');

// Check tokens
const accessToken = localStorage.getItem('accessToken');
const authToken = localStorage.getItem('authToken');

console.log('Access Token:', accessToken ? 'Present' : 'Missing');
console.log('Auth Token:', authToken ? 'Present' : 'Missing');

if (accessToken) {
  console.log('Access Token (first 50 chars):', accessToken.substring(0, 50) + '...');
}

// Test API call
const testApiCall = async () => {
  try {
    const token = accessToken || authToken;
    if (!token) {
      console.error('No token found in localStorage');
      return;
    }

    const response = await fetch('https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev/api/stocks/screen?page=1&limit=5', {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      }
    });

    console.log('Response Status:', response.status);
    console.log('Response Headers:', Object.fromEntries(response.headers.entries()));
    
    const data = await response.text();
    console.log('Response Data:', data.substring(0, 500));
    
  } catch (error) {
    console.error('API Test Error:', error);
  }
};

testApiCall();