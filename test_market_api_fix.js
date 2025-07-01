#!/usr/bin/env node
/**
 * Test script to verify the market API fix is working
 */

const https = require('https');

const API_BASE = 'https://ye9syrnj8c.execute-api.us-east-1.amazonaws.com/dev';

function testEndpoint(path, description) {
  return new Promise((resolve, reject) => {
    console.log(`\n🧪 Testing: ${description}`);
    console.log(`📡 GET ${API_BASE}${path}`);
    
    const req = https.get(`${API_BASE}${path}`, (res) => {
      let data = '';
      
      res.on('data', (chunk) => {
        data += chunk;
      });
      
      res.on('end', () => {
        try {
          const jsonData = JSON.parse(data);
          console.log(`✅ Status: ${res.statusCode}`);
          
          if (res.statusCode === 200) {
            // Check response structure
            console.log(`📊 Response structure:`, Object.keys(jsonData));
            
            if (path === '/market/overview') {
              // Specific checks for market overview
              const hasData = jsonData.data;
              const hasSentiment = hasData && hasData.sentiment_indicators;
              const hasBreadth = hasData && hasData.market_breadth;
              const hasMarketCap = hasData && hasData.market_cap;
              const hasEconomic = hasData && hasData.economic_indicators;
              
              console.log(`  📈 Has data: ${!!hasData}`);
              console.log(`  😊 Has sentiment_indicators: ${!!hasSentiment}`);
              console.log(`  📊 Has market_breadth: ${!!hasBreadth}`);
              console.log(`  💰 Has market_cap: ${!!hasMarketCap}`);
              console.log(`  🏛️ Has economic_indicators: ${!!hasEconomic}`);
              
              if (hasSentiment) {
                console.log(`  🎯 Sentiment keys: ${Object.keys(jsonData.data.sentiment_indicators)}`);
              }
            }
            
            console.log(`✅ ${description}: SUCCESS`);
            resolve({ success: true, data: jsonData });
          } else {
            console.log(`❌ ${description}: HTTP ${res.statusCode}`);
            console.log(`📄 Response:`, jsonData);
            resolve({ success: false, status: res.statusCode, data: jsonData });
          }
        } catch (e) {
          console.log(`❌ ${description}: Invalid JSON`);
          console.log(`📄 Raw response:`, data.substring(0, 200));
          resolve({ success: false, error: 'Invalid JSON', data: data });
        }
      });
    });
    
    req.on('error', (err) => {
      console.log(`❌ ${description}: Network error`);
      console.log(`🔥 Error:`, err.message);
      resolve({ success: false, error: err.message });
    });
    
    req.setTimeout(10000, () => {
      console.log(`❌ ${description}: Timeout`);
      req.destroy();
      resolve({ success: false, error: 'Timeout' });
    });
  });
}

async function runTests() {
  console.log('🚀 Testing Market API Fix');
  console.log('================================');
  
  const tests = [
    { path: '/market/debug', description: 'Debug endpoint (verify tables)' },
    { path: '/market/overview', description: 'Market overview (main fix)' },
    { path: '/market/breadth', description: 'Market breadth' },
    { path: '/market/sentiment/history?days=7', description: 'Sentiment history' },
  ];
  
  const results = [];
  
  for (const test of tests) {
    const result = await testEndpoint(test.path, test.description);
    results.push({ ...test, ...result });
    
    // Wait between tests to avoid rate limiting
    await new Promise(resolve => setTimeout(resolve, 1000));
  }
  
  // Summary
  console.log('\n📋 TEST SUMMARY');
  console.log('================');
  
  const successful = results.filter(r => r.success);
  const failed = results.filter(r => !r.success);
  
  console.log(`✅ Successful: ${successful.length}/${results.length}`);
  console.log(`❌ Failed: ${failed.length}/${results.length}`);
  
  if (failed.length > 0) {
    console.log('\n🔍 Failed Tests:');
    failed.forEach(test => {
      console.log(`  ❌ ${test.description}: ${test.error || test.status || 'Unknown error'}`);
    });
  }
  
  // Key result for market overview
  const overviewTest = results.find(r => r.path === '/market/overview');
  if (overviewTest && overviewTest.success) {
    console.log('\n🎉 MARKET OVERVIEW FIX: SUCCESS');
    console.log('The frontend should now be able to load market data correctly!');
  } else {
    console.log('\n⚠️ MARKET OVERVIEW FIX: STILL HAS ISSUES');
    console.log('The frontend may still show loading errors.');
  }
  
  console.log('\n✅ Test completed!');
}

// Run the tests
runTests().catch(console.error);