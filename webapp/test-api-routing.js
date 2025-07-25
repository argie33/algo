#!/usr/bin/env node

/**
 * API Routing Test Script
 * Tests if API endpoints return JSON or HTML to diagnose routing issues
 */

const https = require('https');

const BASE_URL = 'https://d1zb7knau41vl9.cloudfront.net';

const API_ENDPOINTS = [
  '/api/health',
  '/api/stocks',
  '/api/stocks/popular',
  '/api/portfolio/holdings',
  '/api/market/overview',
  '/api/market/sentiment',
  '/api/trading/signals/daily',
  '/api/dashboard',
  '/api/screener'
];

async function testEndpoint(endpoint) {
  return new Promise((resolve) => {
    const url = `${BASE_URL}${endpoint}`;
    console.log(`\n🔍 Testing: ${url}`);
    
    const options = {
      headers: {
        'Accept': 'application/json',
        'User-Agent': 'API-Routing-Test/1.0'
      }
    };

    const req = https.get(url, options, (res) => {
      let data = '';
      
      res.on('data', (chunk) => {
        data += chunk;
      });
      
      res.on('end', () => {
        const contentType = res.headers['content-type'] || '';
        const isHTML = data.includes('<!DOCTYPE html>') || contentType.includes('text/html');
        const isJSON = contentType.includes('application/json');
        
        console.log(`   Status: ${res.statusCode}`);
        console.log(`   Content-Type: ${contentType}`);
        console.log(`   Response Type: ${isHTML ? '🔴 HTML' : isJSON ? '🟢 JSON' : '🟡 OTHER'}`);
        console.log(`   Size: ${data.length} bytes`);
        
        if (isHTML) {
          console.log(`   ❌ ROUTING ISSUE: Receiving HTML instead of JSON`);
        } else if (isJSON) {
          console.log(`   ✅ CORRECT: JSON response received`);
          // Try to parse JSON
          try {
            const parsed = JSON.parse(data);
            console.log(`   📊 JSON Structure: ${Object.keys(parsed).join(', ')}`);
          } catch (e) {
            console.log(`   ⚠️  Invalid JSON: ${e.message}`);
          }
        } else {
          console.log(`   ⚠️  Unexpected content type`);
        }
        
        if (data.length > 0 && data.length < 500) {
          console.log(`   Preview: ${data.substring(0, 200)}...`);
        }
        
        resolve({
          endpoint,
          status: res.statusCode,
          contentType,
          isHTML,
          isJSON,
          size: data.length,
          working: isJSON && res.statusCode === 200
        });
      });
    });
    
    req.on('error', (error) => {
      console.log(`   ❌ ERROR: ${error.message}`);
      resolve({
        endpoint,
        status: 0,
        contentType: '',
        isHTML: false,
        isJSON: false,
        size: 0,
        working: false,
        error: error.message
      });
    });
    
    req.setTimeout(10000, () => {
      req.destroy();
      console.log(`   ⏱️  TIMEOUT`);
      resolve({
        endpoint,
        status: 0,
        contentType: '',
        isHTML: false,
        isJSON: false,
        size: 0,
        working: false,
        error: 'Timeout'
      });
    });
  });
}

async function runTests() {
  console.log('🧪 API Routing Diagnostic Test');
  console.log('=====================================');
  console.log(`Base URL: ${BASE_URL}`);
  console.log(`Testing ${API_ENDPOINTS.length} endpoints...\n`);

  const results = [];
  
  for (const endpoint of API_ENDPOINTS) {
    const result = await testEndpoint(endpoint);
    results.push(result);
    
    // Add delay between requests
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  
  console.log('\n📋 SUMMARY REPORT');
  console.log('==================');
  
  const working = results.filter(r => r.working);
  const htmlResponses = results.filter(r => r.isHTML);
  const errors = results.filter(r => r.error);
  
  console.log(`✅ Working endpoints: ${working.length}/${results.length}`);
  console.log(`🔴 HTML responses: ${htmlResponses.length}/${results.length}`);
  console.log(`❌ Errors: ${errors.length}/${results.length}`);
  
  if (htmlResponses.length > 0) {
    console.log('\n🚨 ROUTING ISSUE DETECTED');
    console.log('==========================');
    console.log('Endpoints returning HTML instead of JSON:');
    htmlResponses.forEach(r => console.log(`   - ${r.endpoint}`));
    
    console.log('\n🔧 RECOMMENDED FIX:');
    console.log('1. Check CloudFront distribution behaviors');
    console.log('2. Ensure /api/* routes forward to Lambda function');
    console.log('3. Verify API Gateway configuration');
    console.log('4. Test with curl: curl -H "Accept: application/json" ' + BASE_URL + '/api/health');
  }
  
  if (working.length === results.length) {
    console.log('\n🎉 ALL ENDPOINTS WORKING CORRECTLY!');
  }
  
  if (working.length > 0) {
    console.log('\n✅ Working endpoints:');
    working.forEach(r => console.log(`   - ${r.endpoint}`));
  }
  
  console.log('\n📊 DETAILED RESULTS:');
  console.log('=====================');
  results.forEach(r => {
    const status = r.working ? '✅' : r.isHTML ? '🔴' : '❌';
    console.log(`${status} ${r.endpoint.padEnd(30)} ${r.status} ${r.contentType}`);
  });
}

// Run tests
runTests().catch(console.error);