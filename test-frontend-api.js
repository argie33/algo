const axios = require('axios');

const API_URL = 'https://ye9syrnj8c.execute-api.us-east-1.amazonaws.com/dev';

async function testFrontendAPI() {
  console.log('🧪 Testing Frontend API Access');
  console.log(`📡 API URL: ${API_URL}`);
  
  try {
    // Test basic health check
    console.log('\n1. Testing Health Check...');
    const healthResponse = await axios.get(`${API_URL}/health?quick=true`);
    console.log(`✅ Health Check: ${healthResponse.status}`, healthResponse.data.status);
    
    // Test portfolio performance (key endpoint for performance page)
    console.log('\n2. Testing Portfolio Performance...');
    const perfResponse = await axios.get(`${API_URL}/portfolio/performance?timeframe=1Y`);
    console.log(`✅ Portfolio Performance: ${perfResponse.status}`);
    console.log(`📊 Performance data points: ${perfResponse.data.data.performance.length}`);
    console.log(`💰 Total return: ${perfResponse.data.data.metrics.totalReturnPercent}%`);
    
    // Test portfolio analytics (main issue endpoint)
    console.log('\n3. Testing Portfolio Analytics...');
    const analyticsResponse = await axios.get(`${API_URL}/portfolio/analytics?timeframe=1Y`);
    console.log(`✅ Portfolio Analytics: ${analyticsResponse.status}`);
    console.log(`📈 Holdings count: ${analyticsResponse.data.data.holdings.length}`);
    console.log(`🏢 Portfolio value: $${analyticsResponse.data.data.summary.totalValue.toLocaleString()}`);
    
    console.log('\n🎉 All API tests passed! The AWS API is working correctly.');
    console.log('💡 The issue might be with frontend authentication or configuration.');
    
  } catch (error) {
    console.error('\n❌ API Test failed:', error.message);
    if (error.response) {
      console.error(`Status: ${error.response.status}`);
      console.error('Response:', error.response.data);
    }
  }
}

testFrontendAPI();