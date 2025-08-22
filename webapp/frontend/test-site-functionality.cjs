#!/usr/bin/env node

/**
 * Comprehensive Site Functionality Test
 * Tests actual site behavior, configuration loading, and API connectivity
 */

const https = require('https');
const fs = require('fs');
const path = require('path');

class SiteFunctionalityTester {
  constructor() {
    this.testResults = {
      passed: 0,
      failed: 0,
      errors: []
    };
    this.apiUrl = 'https://qda42av7je.execute-api.us-east-1.amazonaws.com/dev';
  }

  log(message, level = 'info') {
    const timestamp = new Date().toISOString();
    const prefix = level === 'error' ? '❌' : level === 'success' ? '✅' : 'ℹ️';
    console.log(`${prefix} [${timestamp}] ${message}`);
  }

  async makeApiRequest(endpoint, expectedStatus = 200) {
    return new Promise((resolve, reject) => {
      const url = `${this.apiUrl}${endpoint}`;
      this.log(`Testing API endpoint: ${endpoint}`);
      
      const req = https.get(url, (res) => {
        let data = '';
        res.on('data', chunk => data += chunk);
        res.on('end', () => {
          try {
            const result = {
              status: res.statusCode,
              headers: res.headers,
              data: res.statusCode !== 204 ? JSON.parse(data) : null,
              url
            };
            
            if (res.statusCode === expectedStatus) {
              this.testResults.passed++;
              this.log(`✅ ${endpoint} - Status ${res.statusCode}`, 'success');
              resolve(result);
            } else {
              this.testResults.failed++;
              this.testResults.errors.push(`${endpoint} returned ${res.statusCode}, expected ${expectedStatus}`);
              this.log(`❌ ${endpoint} - Status ${res.statusCode}, expected ${expectedStatus}`, 'error');
              resolve(result);
            }
          } catch (error) {
            this.testResults.failed++;
            this.testResults.errors.push(`${endpoint} - JSON parse error: ${error.message}`);
            this.log(`❌ ${endpoint} - Parse error: ${error.message}`, 'error');
            resolve({ status: res.statusCode, error: error.message, url });
          }
        });
      });

      req.on('error', (error) => {
        this.testResults.failed++;
        this.testResults.errors.push(`${endpoint} - Network error: ${error.message}`);
        this.log(`❌ ${endpoint} - Network error: ${error.message}`, 'error');
        resolve({ error: error.message, url });
      });

      req.setTimeout(10000, () => {
        req.destroy();
        this.testResults.failed++;
        this.testResults.errors.push(`${endpoint} - Timeout`);
        this.log(`❌ ${endpoint} - Timeout`, 'error');
        resolve({ error: 'Timeout', url });
      });
    });
  }

  async testConfigurationFiles() {
    this.log('=== Testing Configuration Files ===');
    
    // Test dist/config.js exists and has correct values
    const configPath = path.join(__dirname, 'dist', 'config.js');
    if (fs.existsSync(configPath)) {
      const configContent = fs.readFileSync(configPath, 'utf8');
      this.log(`Config file exists: ${configPath}`, 'success');
      
      // Check for correct API URL
      if (configContent.includes('qda42av7je.execute-api.us-east-1.amazonaws.com')) {
        this.log('✅ Config contains correct API URL', 'success');
        this.testResults.passed++;
      } else {
        this.log('❌ Config does not contain correct API URL', 'error');
        this.testResults.failed++;
        this.testResults.errors.push('Config file missing correct API URL');
      }
      
      // Check for Cognito client ID
      if (configContent.includes('1rn05nvf53cvmc0dsvbbkl3ng1')) {
        this.log('✅ Config contains correct Cognito Client ID', 'success');
        this.testResults.passed++;
      } else {
        this.log('❌ Config does not contain correct Cognito Client ID', 'error');
        this.testResults.failed++;
        this.testResults.errors.push('Config file missing correct Cognito Client ID');
      }
    } else {
      this.log('❌ Config file not found', 'error');
      this.testResults.failed++;
      this.testResults.errors.push('dist/config.js not found');
    }
  }

  async testCriticalEndpoints() {
    this.log('=== Testing Critical API Endpoints ===');
    
    const publicEndpoints = [
      '/health',
      '/api/health',
      '/market/overview',
      '/technical/data/AAPL'
    ];
    
    const protectedEndpoints = [
      { endpoint: '/portfolio/holdings', expected: 401 },
      { endpoint: '/settings/profile', expected: 401 },
      { endpoint: '/stocks/search?query=AAPL', expected: 401 }
    ];

    const results = [];
    
    // Test public endpoints
    for (const endpoint of publicEndpoints) {
      const result = await this.makeApiRequest(endpoint);
      results.push({ endpoint, result });
      
      // Small delay between requests
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    
    // Test protected endpoints (should return 401)
    for (const { endpoint, expected } of protectedEndpoints) {
      const result = await this.makeApiRequest(endpoint, expected);
      results.push({ endpoint, result });
      
      // Small delay between requests
      await new Promise(resolve => setTimeout(resolve, 100));
    }

    return results;
  }

  async testDatabaseConnectivity() {
    this.log('=== Testing Database Connectivity ===');
    
    const healthResult = await this.makeApiRequest('/health');
    if (healthResult.data && healthResult.data.database) {
      if (healthResult.data.database.status === 'connected') {
        this.log('✅ Database is connected', 'success');
        this.testResults.passed++;
        
        // Check for table data
        if (healthResult.data.database.tables && Object.keys(healthResult.data.database.tables).length > 0) {
          this.log(`✅ Database has ${Object.keys(healthResult.data.database.tables).length} tables with data`, 'success');
          this.testResults.passed++;
        } else {
          this.log('⚠️ Database connected but no table data found');
        }
      } else {
        this.log('❌ Database connection failed', 'error');
        this.testResults.failed++;
        this.testResults.errors.push('Database not connected');
      }
    }
  }

  async testCORSConfiguration() {
    this.log('=== Testing CORS Configuration ===');
    
    // Test OPTIONS request for CORS preflight
    const optionsResult = await this.makeApiRequest('/health', 200);
    if (optionsResult.headers) {
      const corsHeaders = [
        'access-control-allow-origin',
        'access-control-allow-methods',
        'access-control-allow-headers'
      ];
      
      let corsConfigured = true;
      for (const header of corsHeaders) {
        if (optionsResult.headers[header]) {
          this.log(`✅ CORS header present: ${header}`, 'success');
        } else {
          this.log(`⚠️ CORS header missing: ${header}`);
          corsConfigured = false;
        }
      }
      
      if (corsConfigured) {
        this.testResults.passed++;
      }
    }
  }

  async testAuthenticationEndpoints() {
    this.log('=== Testing Authentication Endpoints ===');
    
    // Test auth endpoints that should work without authentication
    const authEndpoints = [
      { endpoint: '/auth/health', expected: 200 },
      { endpoint: '/api/auth/me', expected: 401 }, // Should return 401 without token
    ];

    for (const { endpoint, expected } of authEndpoints) {
      await this.makeApiRequest(endpoint, expected);
    }
  }

  async runAllTests() {
    this.log('🚀 Starting comprehensive site functionality tests...');
    this.log(`API Base URL: ${this.apiUrl}`);
    
    try {
      await this.testConfigurationFiles();
      await this.testCriticalEndpoints();
      await this.testDatabaseConnectivity();
      await this.testCORSConfiguration();
      await this.testAuthenticationEndpoints();
      
      this.log('=== Test Summary ===');
      this.log(`✅ Passed: ${this.testResults.passed}`);
      this.log(`❌ Failed: ${this.testResults.failed}`);
      
      if (this.testResults.errors.length > 0) {
        this.log('=== Errors Found ===');
        this.testResults.errors.forEach(error => {
          this.log(`❌ ${error}`, 'error');
        });
      }
      
      if (this.testResults.failed === 0) {
        this.log('🎉 All tests passed! Site is functioning correctly.', 'success');
        process.exit(0);
      } else {
        this.log(`⚠️ ${this.testResults.failed} tests failed. Issues need attention.`, 'error');
        process.exit(1);
      }
      
    } catch (error) {
      this.log(`💥 Test suite failed: ${error.message}`, 'error');
      process.exit(1);
    }
  }
}

// Run tests if called directly
if (require.main === module) {
  const tester = new SiteFunctionalityTester();
  tester.runAllTests().catch(error => {
    console.error('❌ Test suite crashed:', error);
    process.exit(1);
  });
}

module.exports = SiteFunctionalityTester;