// Simple Node.js script to test the React app and debug authentication

const { spawn } = require('child_process');

console.log('🧪 Starting authentication flow debug...');

// Test if the dev server is accessible
const testServer = async () => {
  try {
    const response = await fetch('http://localhost:3000');
    console.log('✅ Dev server is responsive on port 3000');
    
    // Check if the HTML contains the React app structure
    const html = await response.text();
    if (html.includes('<div id="root">')) {
      console.log('✅ React app HTML structure detected');
    } else {
      console.log('❌ React app structure not found in HTML');
    }
    
    if (html.includes('main.jsx') || html.includes('vite')) {
      console.log('✅ Vite dev server is serving the React app');
    }
    
  } catch (error) {
    console.error('❌ Cannot connect to dev server:', error.message);
    console.log('💡 Make sure dev server is running with: npm run dev');
    return false;
  }
  return true;
};

// Check for common React/auth issues
const checkForCommonIssues = async () => {
  console.log('\n🔍 Checking for common issues...');
  
  // Check if there are JS errors in the console by looking at the network requests
  try {
    // Check main.jsx is loading
    const mainJsResponse = await fetch('http://localhost:3000/src/main.jsx');
    if (mainJsResponse.ok) {
      console.log('✅ main.jsx is accessible');
    } else {
      console.log('❌ main.jsx failed to load:', mainJsResponse.status);
    }
  } catch (error) {
    console.log('❌ Could not test main.jsx loading');
  }
  
  // Test API connectivity from this script
  console.log('\n🔌 Testing API connectivity...');
  try {
    const healthResponse = await fetch('https://ye9syrnj8c.execute-api.us-east-1.amazonaws.com/dev/health');
    const healthData = await healthResponse.json();
    console.log('✅ API health check successful:', healthData.status);
    
    const perfResponse = await fetch('https://ye9syrnj8c.execute-api.us-east-1.amazonaws.com/dev/portfolio/performance?timeframe=1Y');
    const perfData = await perfResponse.json();
    console.log('✅ Portfolio performance API working, data points:', perfData.data?.performance?.length || 0);
    
  } catch (error) {
    console.log('❌ API connectivity test failed:', error.message);
  }
};

const investigateIssue = async () => {
  console.log('🕵️ Investigating portfolio performance page issue...\n');
  
  const serverOk = await testServer();
  if (!serverOk) {
    return;
  }
  
  await checkForCommonIssues();
  
  console.log('\n💡 Recommendations:');
  console.log('1. Open browser to: http://localhost:3000/portfolio/performance');
  console.log('2. Open browser dev tools (F12)');
  console.log('3. Check Console tab for JavaScript errors');
  console.log('4. Check Network tab for failed requests');
  console.log('5. If page is white, look for:');
  console.log('   - Authentication loading hanging');
  console.log('   - API calls failing');
  console.log('   - React component errors');
  console.log('   - Missing environment variables');
  
  console.log('\n🔧 Manual debugging steps:');
  console.log('1. Try navigating to: http://localhost:3000/test-api');
  console.log('2. This should show API test results');
  console.log('3. If that works, the issue is specific to PortfolioPerformance component');
  console.log('4. If that fails, the issue is with API configuration');
  
  console.log('\n🎯 Most likely causes:');
  console.log('- Authentication context loading indefinitely');
  console.log('- CORS issues between localhost:3000 and AWS API');
  console.log('- Missing authentication tokens');
  console.log('- React component infinite re-render loop');
};

investigateIssue().catch(console.error);