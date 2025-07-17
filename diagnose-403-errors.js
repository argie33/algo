#!/usr/bin/env node

const axios = require('axios');

const API_BASE = 'https://ye9syrnj8c.execute-api.us-east-1.amazonaws.com/dev';

async function diagnose403Errors() {
  console.log('🔍 Diagnosing 403 Errors\n');
  
  // Test different endpoints with different approaches
  const tests = [
    {
      name: 'Basic root endpoint',
      url: '',
      method: 'GET'
    },
    {
      name: 'Health endpoint without /api prefix',
      url: '/health',
      method: 'GET'
    },
    {
      name: 'Health endpoint with /api prefix',
      url: '/api/health',
      method: 'GET'
    },
    {
      name: 'Health endpoint with query param',
      url: '/api/health?quick=true',
      method: 'GET'
    },
    {
      name: 'OPTIONS request (CORS preflight)',
      url: '/api/health',
      method: 'OPTIONS'
    }
  ];
  
  for (const test of tests) {
    try {
      console.log(`\n🧪 Testing: ${test.name}`);
      console.log(`   URL: ${API_BASE}${test.url}`);
      console.log(`   Method: ${test.method}`);
      
      const config = {
        method: test.method,
        url: `${API_BASE}${test.url}`,
        timeout: 10000,
        validateStatus: () => true, // Don't throw on any status
        headers: {
          'User-Agent': 'API-Health-Check/1.0',
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        }
      };
      
      const response = await axios(config);
      
      console.log(`   Status: ${response.status}`);
      console.log(`   Headers:`, JSON.stringify(response.headers, null, 2));
      
      if (response.data) {
        console.log(`   Response:`, JSON.stringify(response.data, null, 2));
      }
      
    } catch (error) {
      console.log(`   ERROR: ${error.message}`);
      if (error.response) {
        console.log(`   Status: ${error.response.status}`);
        console.log(`   Headers:`, JSON.stringify(error.response.headers, null, 2));
        console.log(`   Data:`, JSON.stringify(error.response.data, null, 2));
      }
    }
  }
  
  // Test with different headers
  console.log('\n\n🔧 Testing with different headers...');
  
  const headerTests = [
    {
      name: 'With Origin header',
      headers: {
        'Origin': 'https://example.com',
        'User-Agent': 'API-Health-Check/1.0'
      }
    },
    {
      name: 'With Authorization header (empty)',
      headers: {
        'Authorization': 'Bearer ',
        'User-Agent': 'API-Health-Check/1.0'
      }
    },
    {
      name: 'With minimal headers',
      headers: {
        'User-Agent': 'curl/7.68.0'
      }
    }
  ];
  
  for (const headerTest of headerTests) {
    try {
      console.log(`\n🧪 Testing: ${headerTest.name}`);
      
      const response = await axios({
        method: 'GET',
        url: `${API_BASE}/api/health?quick=true`,
        headers: headerTest.headers,
        timeout: 10000,
        validateStatus: () => true
      });
      
      console.log(`   Status: ${response.status}`);
      console.log(`   Response:`, JSON.stringify(response.data, null, 2));
      
    } catch (error) {
      console.log(`   ERROR: ${error.message}`);
    }
  }
  
  // Test direct Lambda invocation format
  console.log('\n\n🧪 Testing direct Lambda format...');
  
  try {
    const response = await axios({
      method: 'GET',
      url: `${API_BASE}/`,
      timeout: 10000,
      validateStatus: () => true
    });
    
    console.log(`Direct root access - Status: ${response.status}`);
    console.log(`Response:`, JSON.stringify(response.data, null, 2));
    
  } catch (error) {
    console.log(`Direct root ERROR: ${error.message}`);
  }
}

diagnose403Errors().catch(console.error);