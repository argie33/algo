#!/usr/bin/env node
/**
 * Frontend Configuration Test
 * Validates frontend configuration and API integration
 */

const https = require('https');
const fs = require('fs');
const path = require('path');

const API_URL = 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev';
const FRONTEND_CONFIG_PATH = '../frontend/public/config.js';

// Frontend-specific endpoints that the React app depends on
const FRONTEND_ENDPOINTS = [
  {
    path: '/',
    name: 'Root API',
    required: true,
    frontendUse: 'Initial health check'
  },
  {
    path: '/api/health',
    name: 'Health Check',
    required: true,
    frontendUse: 'System status monitoring'
  },
  {
    path: '/api/settings/api-keys',
    name: 'API Keys Management',
    required: true,
    frontendUse: 'User onboarding and settings'
  },
  {
    path: '/api/settings/notifications',
    name: 'Notification Settings',
    required: false,
    frontendUse: 'User preferences'
  },
  {
    path: '/api/settings/theme',
    name: 'Theme Settings',
    required: false,
    frontendUse: 'UI customization'
  },
  {
    path: '/api/stocks/sectors',
    name: 'Stock Sectors',
    required: true,
    frontendUse: 'Market data display'
  },
  {
    path: '/api/portfolio/holdings',
    name: 'Portfolio Holdings',
    required: true,
    frontendUse: 'Portfolio page'
  },
  {
    path: '/api/live-data/metrics',
    name: 'Live Data Metrics',
    required: false,
    frontendUse: 'Real-time monitoring'
  },
  {
    path: '/api/market-overview',
    name: 'Market Overview',
    required: false,
    frontendUse: 'Dashboard page'
  }
];

async function makeRequest(path) {
  return new Promise((resolve) => {
    const url = `${API_URL}${path}`;
    
    const req = https.get(url, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          resolve({
            path,
            statusCode: res.statusCode,
            data: JSON.parse(data),
            headers: res.headers,
            timestamp: new Date().toISOString()
          });
        } catch (e) {
          resolve({
            path,
            statusCode: res.statusCode,
            data: data,
            headers: res.headers,
            parseError: true,
            timestamp: new Date().toISOString()
          });
        }
      });
    });
    
    req.on('error', (err) => {
      resolve({
        path,
        error: err.message,
        timestamp: new Date().toISOString()
      });
    });
    
    req.setTimeout(10000);
    req.end();
  });
}

function validateFrontendConfig() {
  console.log('⚙️ Frontend Configuration Validation');
  console.log('-'.repeat(50));
  
  const configResult = {
    configExists: false,
    configValid: false,
    apiUrlCorrect: false,
    cognitoConfigured: false,
    issues: [],
    config: null
  };
  
  try {
    const configPath = path.resolve(__dirname, FRONTEND_CONFIG_PATH);
    
    if (fs.existsSync(configPath)) {
      configResult.configExists = true;
      console.log('✅ Config file exists');
      
      const configContent = fs.readFileSync(configPath, 'utf8');
      
      // Extract config object (simple parsing)
      const configMatch = configContent.match(/window\.__CONFIG__\s*=\s*({[\s\S]*?});/);
      
      if (configMatch) {
        try {
          // Simple evaluation of the config object
          const configStr = configMatch[1];
          const config = eval(`(${configStr})`);
          configResult.config = config;
          configResult.configValid = true;
          
          console.log('✅ Config file is valid JavaScript');
          
          // Check API URL
          if (config.API_URL) {
            configResult.apiUrlCorrect = config.API_URL === API_URL;
            console.log(`📡 API URL: ${config.API_URL}`);
            console.log(`   ${configResult.apiUrlCorrect ? '✅' : '⚠️'} ${configResult.apiUrlCorrect ? 'Matches current API' : 'Different from current API'}`);
          } else {
            configResult.issues.push('API_URL not configured');
            console.log('❌ API_URL not found in config');
          }
          
          // Check Cognito configuration
          if (config.COGNITO) {
            const hasUserPool = config.COGNITO.USER_POOL_ID && !config.COGNITO.USER_POOL_ID.includes('FALLBACK');
            const hasClientId = config.COGNITO.CLIENT_ID && !config.COGNITO.CLIENT_ID.includes('fallback');
            
            configResult.cognitoConfigured = hasUserPool && hasClientId;
            
            console.log(`🔐 Cognito User Pool: ${config.COGNITO.USER_POOL_ID}`);
            console.log(`🔐 Cognito Client ID: ${config.COGNITO.CLIENT_ID}`);
            console.log(`   ${configResult.cognitoConfigured ? '✅' : '❌'} ${configResult.cognitoConfigured ? 'Properly configured' : 'Using fallback values'}`);
            
            if (!configResult.cognitoConfigured) {
              configResult.issues.push('Cognito using fallback values');
            }
          } else {
            configResult.issues.push('COGNITO configuration missing');
            console.log('❌ COGNITO configuration not found');
          }
          
        } catch (evalError) {
          configResult.issues.push(`Config evaluation error: ${evalError.message}`);
          console.log(`❌ Config evaluation failed: ${evalError.message}`);
        }
      } else {
        configResult.issues.push('Config object not found in file');
        console.log('❌ Could not find window.__CONFIG__ in file');
      }
      
    } else {
      configResult.issues.push('Config file does not exist');
      console.log('❌ Config file not found');
    }
    
  } catch (error) {
    configResult.issues.push(`Config validation error: ${error.message}`);
    console.log(`❌ Config validation error: ${error.message}`);
  }
  
  return configResult;
}

function checkCorsHeaders(response) {
  const headers = response.headers || {};
  
  return {
    allowOrigin: headers['access-control-allow-origin'],
    allowMethods: headers['access-control-allow-methods'],
    allowHeaders: headers['access-control-allow-headers'],
    allowCredentials: headers['access-control-allow-credentials']
  };
}

async function testFrontendIntegration() {
  console.log('🌐 Frontend Integration Test');
  console.log('='.repeat(60));
  console.log(`📡 API URL: ${API_URL}`);
  console.log(`🕐 Started: ${new Date().toISOString()}`);
  
  const results = {
    timestamp: new Date().toISOString(),
    apiUrl: API_URL,
    frontendConfig: null,
    endpoints: [],
    cors: {},
    summary: {
      total: FRONTEND_ENDPOINTS.length,
      working: 0,
      required: 0,
      requiredWorking: 0,
      corsIssues: 0
    }
  };
  
  // Validate frontend configuration
  results.frontendConfig = validateFrontendConfig();
  
  // Test each frontend endpoint
  console.log('\n📡 Testing Frontend API Endpoints');
  console.log('-'.repeat(50));
  
  for (const endpoint of FRONTEND_ENDPOINTS) {
    console.log(`\n🔍 ${endpoint.name} (${endpoint.path})`);
    console.log(`   📋 Frontend Use: ${endpoint.frontendUse}`);
    console.log(`   🚨 Required: ${endpoint.required ? 'Yes' : 'No'}`);
    
    if (endpoint.required) {
      results.summary.required++;
    }
    
    const response = await makeRequest(endpoint.path);
    
    const endpointResult = {
      name: endpoint.name,
      path: endpoint.path,
      required: endpoint.required,
      frontendUse: endpoint.frontendUse,
      response: response,
      working: false,
      corsOk: false,
      issues: []
    };
    
    if (response.error) {
      console.log(`   ❌ Connection Error: ${response.error}`);
      endpointResult.issues.push(`Connection failed: ${response.error}`);
    } else if (response.statusCode >= 400) {
      console.log(`   ❌ HTTP Error: ${response.statusCode}`);
      endpointResult.issues.push(`HTTP ${response.statusCode}`);
    } else {
      console.log(`   ✅ HTTP Status: ${response.statusCode}`);
      
      // Check response validity
      if (response.parseError) {
        console.log(`   ⚠️ Response: Invalid JSON`);
        endpointResult.issues.push('Invalid JSON response');
      } else if (response.data) {
        if (response.data.success === false) {
          console.log(`   ⚠️ Response: API reported failure`);
          endpointResult.issues.push(`API error: ${response.data.error || 'Unknown'}`);
        } else {
          console.log(`   ✅ Response: Valid data`);
          endpointResult.working = true;
          results.summary.working++;
          
          if (endpoint.required) {
            results.summary.requiredWorking++;
          }
        }
      }
      
      // Check CORS headers
      const corsHeaders = checkCorsHeaders(response);
      
      if (corsHeaders.allowOrigin) {
        console.log(`   ✅ CORS: Allow-Origin: ${corsHeaders.allowOrigin}`);
        endpointResult.corsOk = true;
      } else {
        console.log(`   ❌ CORS: No Allow-Origin header`);
        endpointResult.issues.push('Missing CORS Allow-Origin header');
        results.summary.corsIssues++;
      }
      
      results.cors[endpoint.path] = corsHeaders;
    }
    
    results.endpoints.push(endpointResult);
  }
  
  // Frontend integration assessment
  console.log('\n' + '='.repeat(60));
  console.log('🌐 Frontend Integration Assessment');
  console.log('='.repeat(60));
  
  const workingRate = (results.summary.working / results.summary.total) * 100;
  const requiredRate = results.summary.required > 0 ? 
    (results.summary.requiredWorking / results.summary.required) * 100 : 100;
  
  console.log(`📊 Endpoints Working: ${results.summary.working}/${results.summary.total} (${workingRate.toFixed(1)}%)`);
  console.log(`🚨 Required Working: ${results.summary.requiredWorking}/${results.summary.required} (${requiredRate.toFixed(1)}%)`);
  console.log(`🌐 CORS Issues: ${results.summary.corsIssues}`);
  
  // Configuration assessment
  const config = results.frontendConfig;
  console.log('\n⚙️ Configuration Status:');
  console.log(`   📁 Config File: ${config.configExists ? '✅ Exists' : '❌ Missing'}`);
  console.log(`   📝 Config Valid: ${config.configValid ? '✅ Valid' : '❌ Invalid'}`);
  console.log(`   📡 API URL: ${config.apiUrlCorrect ? '✅ Correct' : '⚠️ Different'}`);
  console.log(`   🔐 Cognito: ${config.cognitoConfigured ? '✅ Configured' : '❌ Fallback Values'}`);
  
  // Overall frontend readiness
  console.log('\n🎯 Frontend Readiness:');
  
  if (requiredRate === 100 && config.configExists && config.configValid && results.summary.corsIssues === 0) {
    console.log('🟢 FRONTEND READY');
    console.log('   ✅ All required endpoints working');
    console.log('   ✅ Configuration is valid');
    console.log('   ✅ No CORS issues detected');
  } else if (requiredRate >= 80) {
    console.log('🟡 FRONTEND PARTIALLY READY');
    console.log('   ✅ Most required endpoints working');
    console.log('   ⚠️ Some issues may affect user experience');
  } else {
    console.log('🔴 FRONTEND NOT READY');
    console.log('   ❌ Critical endpoints not working');
    console.log('   🚫 Frontend will not function properly');
  }
  
  // Recommendations
  console.log('\n🔧 Recommendations:');
  
  if (!config.configExists || !config.configValid) {
    console.log('   📁 Generate proper frontend configuration from CloudFormation outputs');
  }
  
  if (!config.cognitoConfigured) {
    console.log('   🔐 Update Cognito configuration with real values from deployment');
  }
  
  if (results.summary.corsIssues > 0) {
    console.log('   🌐 Fix CORS configuration in API Gateway/Lambda');
  }
  
  if (requiredRate < 100) {
    console.log('   📡 Fix failing required endpoints before frontend deployment');
  }
  
  console.log(`\n✨ Test completed: ${new Date().toISOString()}`);
  
  return results;
}

// Run if called directly
if (require.main === module) {
  testFrontendIntegration().catch(console.error);
}

module.exports = { testFrontendIntegration, validateFrontendConfig };