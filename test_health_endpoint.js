#!/usr/bin/env node

// Test script to check the health endpoint response structure
const https = require('https');
const url = require('url');

const API_URL = 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev/health';

function makeRequest(endpoint) {
  return new Promise((resolve, reject) => {
    const options = {
      ...url.parse(endpoint),
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
        'User-Agent': 'Health-Test-Script'
      }
    };

    const req = https.request(options, (res) => {
      let data = '';
      res.on('data', (chunk) => {
        data += chunk;
      });
      res.on('end', () => {
        try {
          const parsed = JSON.parse(data);
          resolve({ status: res.statusCode, data: parsed });
        } catch (error) {
          reject(new Error(`JSON parse error: ${error.message}`));
        }
      });
    });

    req.on('error', (error) => {
      reject(error);
    });

    req.setTimeout(10000, () => {
      req.abort();
      reject(new Error('Request timeout'));
    });

    req.end();
  });
}

async function testHealthEndpoint() {
  console.log('🧪 Testing Health Endpoint Response Structure');
  console.log('===========================================');
  
  try {
    console.log('🔍 Making request to:', API_URL);
    const response = await makeRequest(API_URL);
    
    console.log('✅ Response Status:', response.status);
    console.log('📊 Response Keys:', Object.keys(response.data));
    console.log('');
    
    if (response.data.database) {
      console.log('🗄️ Database Object Keys:', Object.keys(response.data.database));
      
      if (response.data.database.tables) {
        const tableKeys = Object.keys(response.data.database.tables);
        console.log('📋 Tables Found:', tableKeys.length);
        console.log('📋 Table Names:', tableKeys.slice(0, 10).join(', ') + (tableKeys.length > 10 ? '...' : ''));
        
        if (tableKeys.length > 0) {
          console.log('');
          console.log('📄 Sample Table Data (first table):');
          const firstTable = tableKeys[0];
          console.log(`Table: ${firstTable}`);
          console.log('Data:', JSON.stringify(response.data.database.tables[firstTable], null, 2));
        }
      } else {
        console.log('❌ No tables property found in database object');
      }
      
      if (response.data.database.summary) {
        console.log('');
        console.log('📊 Database Summary:');
        console.log(JSON.stringify(response.data.database.summary, null, 2));
      }
    } else {
      console.log('❌ No database property found in response');
    }
    
    console.log('');
    console.log('🔍 Full Response Structure:');
    console.log(JSON.stringify(response.data, null, 2));
    
  } catch (error) {
    console.error('❌ Test failed:', error.message);
  }
}

testHealthEndpoint();