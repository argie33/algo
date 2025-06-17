#!/usr/bin/env node

// Production API Connectivity Test - Tests actual production endpoints
const axios = require('axios');

// PRODUCTION API BASE URL
const API_BASE = 'https://lzq5jfiv9b.execute-api.us-east-1.amazonaws.com/Prod';

// Test the actual endpoints that your frontend uses
const criticalEndpoints = [
  { path: '', name: 'Root API', expectData: ['message', 'endpoints'] },
  { path: '/health', name: 'Health Check', expectData: ['status', 'database'] },
  { path: '/technical/daily?limit=3', name: 'Technical Data (Daily)', expectData: ['data', 'pagination'] },
  { path: '/technical/daily?symbol=AAPL&limit=2', name: 'Technical Data (AAPL)', expectData: ['data'] },
  { path: '/stocks?limit=5', name: 'Stock Listings', expectData: ['data'] },
  { path: '/market/overview', name: 'Market Overview', expectData: null }, // May or may not have data
  { path: '/financials/AAPL/balance-sheet', name: 'Balance Sheet (AAPL)', expectData: null },
  { path: '/financials/AAPL/income-statement', name: 'Income Statement (AAPL)', expectData: null },
  { path: '/financials/AAPL/cash-flow', name: 'Cash Flow (AAPL)', expectData: null },
  { path: '/calendar/earnings-estimates?limit=3', name: 'Earnings Calendar', expectData: null },
  { path: '/signals/buy', name: 'Buy Signals', expectData: null },
  { path: '/signals/sell', name: 'Sell Signals', expectData: null }
];

async function testEndpoint(endpointConfig) {
  const { path, name, expectData } = endpointConfig;
  const url = `${API_BASE}${path}`;
  const start = Date.now();
  
  try {
    console.log(`Testing: ${name}`);
    console.log(`  URL: ${url}`);
    
    const response = await axios.get(url, {
      timeout: 30000, // Longer timeout for Lambda cold starts
      headers: {
        'Accept': 'application/json',
        'User-Agent': 'FinancialDashboard-ProductionTest/1.0'
      }
    });
    
    const duration = Date.now() - start;
    const dataSize = JSON.stringify(response.data).length;
    
    // Validate response structure
    let validationStatus = '';
    let dataCount = 0;
    
    if (expectData && Array.isArray(expectData)) {
      const missingFields = expectData.filter(field => !response.data.hasOwnProperty(field));
      if (missingFields.length === 0) {
        validationStatus = '✅ Structure OK';
        // Count data items if present
        if (response.data.data && Array.isArray(response.data.data)) {
          dataCount = response.data.data.length;
        }
      } else {
        validationStatus = `⚠️  Missing: ${missingFields.join(', ')}`;
      }
    } else {
      validationStatus = '📊 Data returned';
      if (response.data.data && Array.isArray(response.data.data)) {
        dataCount = response.data.data.length;
      }
    }
    
    console.log(`  ✅ ${response.status} - ${duration}ms - ${dataSize} bytes - ${validationStatus}`);
    if (dataCount > 0) {
      console.log(`  📈 Records: ${dataCount}`);
    }
    
    // Show a meaningful preview
    if (response.data && typeof response.data === 'object') {
      if (response.data.data && Array.isArray(response.data.data) && response.data.data.length > 0) {
        const firstRecord = response.data.data[0];
        const preview = Object.keys(firstRecord).slice(0, 5).join(', ');
        console.log(`  🔍 Sample fields: ${preview}`);
      } else if (response.data.message) {
        console.log(`  💬 Message: ${response.data.message}`);
      } else if (response.data.status) {
        console.log(`  📊 Status: ${response.data.status}`);
      }
    }
    
    return { 
      success: true, 
      status: response.status, 
      duration, 
      dataSize,
      dataCount,
      validation: validationStatus,
      data: response.data 
    };
    
  } catch (error) {
    const duration = Date.now() - start;
    
    if (error.response) {
      console.log(`  ❌ ${error.response.status} - ${duration}ms - ${error.response.statusText}`);
      if (error.response.data && error.response.data.message) {
        console.log(`  💥 Error: ${error.response.data.message}`);
      }
      return { 
        success: false, 
        status: error.response.status, 
        duration, 
        error: error.response.statusText,
        errorDetails: error.response.data
      };
    } else if (error.code === 'ECONNABORTED') {
      console.log(`  ⏰ TIMEOUT - ${duration}ms - Request timed out`);
      return { success: false, status: 'TIMEOUT', duration, error: 'Request timeout' };
    } else {
      console.log(`  🔌 NETWORK ERROR - ${duration}ms - ${error.message}`);
      return { success: false, status: 'NETWORK_ERROR', duration, error: error.message };
    }
  }
}

async function runProductionTests() {
  console.log('🚀 PRODUCTION API CONNECTIVITY TEST');
  console.log('=' .repeat(60));
  console.log(`🌐 Testing Production API: ${API_BASE}`);
  console.log(`⏰ Test started: ${new Date().toISOString()}`);
  console.log('=' .repeat(60));
  
  const results = {};
  let criticalFailures = [];
  
  for (const endpointConfig of criticalEndpoints) {
    console.log('');
    results[endpointConfig.path] = await testEndpoint(endpointConfig);
    
    // Track critical failures
    if (!results[endpointConfig.path].success) {
      criticalFailures.push({
        name: endpointConfig.name,
        path: endpointConfig.path,
        error: results[endpointConfig.path].error
      });
    }
    
    // Small delay between requests
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  
  console.log('\n' + '=' .repeat(60));
  console.log('📊 PRODUCTION TEST SUMMARY');
  console.log('=' .repeat(60));
  
  let successCount = 0;
  let totalDataRecords = 0;
  let totalCount = criticalEndpoints.length;
  
  for (let i = 0; i < criticalEndpoints.length; i++) {
    const config = criticalEndpoints[i];
    const result = results[config.path];
    
    const status = result.success ? '✅' : '❌';
    const statusCode = result.status || 'N/A';
    const duration = result.duration || 0;
    const dataInfo = result.dataCount > 0 ? ` (${result.dataCount} records)` : '';
    
    console.log(`${status} ${config.name.padEnd(25)} - ${statusCode} - ${duration}ms${dataInfo}`);
    
    if (result.success) {
      successCount++;
      totalDataRecords += (result.dataCount || 0);
    }
  }
  
  console.log('');
  console.log(`🎯 SUCCESS RATE: ${successCount}/${totalCount} (${Math.round(successCount/totalCount*100)}%)`);
  console.log(`📈 TOTAL DATA RECORDS: ${totalDataRecords}`);
  
  if (criticalFailures.length > 0) {
    console.log('');
    console.log('🚨 CRITICAL ISSUES:');
    criticalFailures.forEach(failure => {
      console.log(`   ❌ ${failure.name}: ${failure.error}`);
    });
  }
  
  // Overall health assessment
  console.log('');
  console.log('🏥 OVERALL HEALTH:');
  if (successCount === totalCount) {
    console.log('   💚 EXCELLENT - All endpoints working perfectly');
  } else if (successCount >= totalCount * 0.8) {
    console.log('   💛 GOOD - Most endpoints working, minor issues');
  } else if (successCount >= totalCount * 0.5) {
    console.log('   🧡 DEGRADED - Significant issues detected');
  } else {
    console.log('   ❤️  CRITICAL - Major system problems');
  }
  
  console.log('');
  console.log(`⏰ Test completed: ${new Date().toISOString()}`);
  console.log('=' .repeat(60));
}

// Run the production tests
runProductionTests().catch(console.error);
