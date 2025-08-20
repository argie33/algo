const https = require('https');
const { URL } = require('url');

/**
 * Complete Flow Validation Script
 * Tests the entire stack: Frontend → API Gateway → Lambda → Database → External APIs
 */

class CompleteFlowValidator {
  constructor(baseUrl = null) {
    this.baseUrl = baseUrl || process.env.API_GATEWAY_URL || 'https://your-api-gateway.execute-api.us-east-1.amazonaws.com/dev';
    this.results = {
      timestamp: new Date().toISOString(),
      baseUrl: this.baseUrl,
      tests: [],
      summary: {
        passed: 0,
        failed: 0,
        warnings: 0
      }
    };
    this.authToken = null;
  }

  /**
   * Log test result
   */
  logResult(testName, success, message, data = null) {
    const result = {
      test: testName,
      success: success,
      message: message,
      data: data,
      timestamp: new Date().toISOString()
    };
    
    this.results.tests.push(result);
    
    if (success) {
      this.results.summary.passed++;
      console.log(`✅ ${testName}: ${message}`);
    } else {
      this.results.summary.failed++;
      console.error(`❌ ${testName}: ${message}`);
    }
    
    if (data) {
      console.log(`   Data:`, JSON.stringify(data, null, 2));
    }
  }

  /**
   * Make HTTP request
   */
  async makeRequest(path, method = 'GET', body = null, headers = {}) {
    return new Promise((resolve, reject) => {
      const url = new URL(path, this.baseUrl);
      
      const options = {
        hostname: url.hostname,
        port: url.port || 443,
        path: url.pathname + url.search,
        method: method,
        headers: {
          'Content-Type': 'application/json',
          'User-Agent': 'CompleteFlowValidator/1.0',
          ...headers
        }
      };

      if (body) {
        const bodyStr = JSON.stringify(body);
        options.headers['Content-Length'] = Buffer.byteLength(bodyStr);
      }

      const req = https.request(options, (res) => {
        let data = '';
        
        res.on('data', (chunk) => {
          data += chunk;
        });
        
        res.on('end', () => {
          try {
            const response = {
              statusCode: res.statusCode,
              headers: res.headers,
              body: data ? JSON.parse(data) : null
            };
            resolve(response);
          } catch (error) {
            resolve({
              statusCode: res.statusCode,
              headers: res.headers,
              body: data,
              parseError: error.message
            });
          }
        });
      });

      req.on('error', (error) => {
        reject(error);
      });

      if (body) {
        req.write(JSON.stringify(body));
      }

      req.end();
    });
  }

  /**
   * Test API Gateway accessibility
   */
  async testApiGateway() {
    console.log('\n🧪 Testing API Gateway Accessibility...');
    
    try {
      const response = await this.makeRequest('/');
      
      const success = response.statusCode === 200;
      const data = {
        statusCode: response.statusCode,
        hasBody: !!response.body,
        corsHeaders: {
          'access-control-allow-origin': response.headers['access-control-allow-origin'],
          'access-control-allow-methods': response.headers['access-control-allow-methods'],
          'access-control-allow-headers': response.headers['access-control-allow-headers']
        }
      };
      
      this.logResult(
        'API Gateway Accessibility',
        success,
        success ? 'API Gateway is accessible' : `API Gateway returned ${response.statusCode}`,
        data
      );
      
      return success;
    } catch (error) {
      this.logResult(
        'API Gateway Accessibility',
        false,
        `API Gateway connection failed: ${error.message}`,
        { error: error.name, code: error.code }
      );
      return false;
    }
  }

  /**
   * Test CORS preflight
   */
  async testCORSPreflight() {
    console.log('\n🧪 Testing CORS Preflight...');
    
    try {
      const response = await this.makeRequest('/api/health', 'OPTIONS', null, {
        'Origin': 'https://example.com',
        'Access-Control-Request-Method': 'GET',
        'Access-Control-Request-Headers': 'authorization'
      });
      
      const success = response.statusCode === 200 || response.statusCode === 204;
      const corsHeaders = {
        'access-control-allow-origin': response.headers['access-control-allow-origin'],
        'access-control-allow-methods': response.headers['access-control-allow-methods'],
        'access-control-allow-headers': response.headers['access-control-allow-headers'],
        'access-control-allow-credentials': response.headers['access-control-allow-credentials']
      };
      
      this.logResult(
        'CORS Preflight',
        success,
        success ? 'CORS preflight successful' : `CORS preflight failed with ${response.statusCode}`,
        { statusCode: response.statusCode, corsHeaders }
      );
      
      return success;
    } catch (error) {
      this.logResult(
        'CORS Preflight',
        false,
        `CORS preflight failed: ${error.message}`,
        { error: error.name, code: error.code }
      );
      return false;
    }
  }

  /**
   * Test Lambda function response
   */
  async testLambdaFunction() {
    console.log('\n🧪 Testing Lambda Function Response...');
    
    try {
      const response = await this.makeRequest('/api/health?quick=true');
      
      const success = response.statusCode === 200;
      const data = {
        statusCode: response.statusCode,
        hasBody: !!response.body,
        bodyType: typeof response.body,
        responseTime: response.headers['x-response-time'],
        lambdaRequestId: response.headers['x-amzn-requestid']
      };
      
      if (response.body && typeof response.body === 'object') {
        data.bodyKeys = Object.keys(response.body);
      }
      
      this.logResult(
        'Lambda Function Response',
        success,
        success ? 'Lambda function responding correctly' : `Lambda function returned ${response.statusCode}`,
        data
      );
      
      return success;
    } catch (error) {
      this.logResult(
        'Lambda Function Response',
        false,
        `Lambda function test failed: ${error.message}`,
        { error: error.name, code: error.code }
      );
      return false;
    }
  }

  /**
   * Test database connectivity through Lambda
   */
  async testDatabaseConnectivity() {
    console.log('\n🧪 Testing Database Connectivity Through Lambda...');
    
    try {
      const response = await this.makeRequest('/api/health');
      
      const success = response.statusCode === 200;
      let dbStatus = 'unknown';
      
      if (response.body && response.body.health) {
        dbStatus = response.body.health.checks?.database || 'unknown';
      }
      
      const data = {
        statusCode: response.statusCode,
        databaseStatus: dbStatus,
        hasHealthChecks: !!(response.body && response.body.health && response.body.health.checks)
      };
      
      this.logResult(
        'Database Connectivity',
        success && dbStatus === 'healthy',
        success ? 
          (dbStatus === 'healthy' ? 'Database connection healthy' : `Database status: ${dbStatus}`) :
          `Database health check failed with ${response.statusCode}`,
        data
      );
      
      return success && dbStatus === 'healthy';
    } catch (error) {
      this.logResult(
        'Database Connectivity',
        false,
        `Database connectivity test failed: ${error.message}`,
        { error: error.name, code: error.code }
      );
      return false;
    }
  }

  /**
   * Test API key service
   */
  async testApiKeyService() {
    console.log('\n🧪 Testing API Key Service...');
    
    try {
      const response = await this.makeRequest('/api/diagnostics/api-key-service');
      
      // Without authentication, this should return 401
      const success = response.statusCode === 401;
      const data = {
        statusCode: response.statusCode,
        hasBody: !!response.body,
        authRequired: response.statusCode === 401
      };
      
      this.logResult(
        'API Key Service',
        success,
        success ? 'API key service requires authentication (correct)' : `Unexpected response: ${response.statusCode}`,
        data
      );
      
      return success;
    } catch (error) {
      this.logResult(
        'API Key Service',
        false,
        `API key service test failed: ${error.message}`,
        { error: error.name, code: error.code }
      );
      return false;
    }
  }

  /**
   * Test authentication endpoints
   */
  async testAuthenticationEndpoints() {
    console.log('\n🧪 Testing Authentication Endpoints...');
    
    try {
      const response = await this.makeRequest('/api/auth/health');
      
      const success = response.statusCode === 200;
      const data = {
        statusCode: response.statusCode,
        hasBody: !!response.body,
        authEndpointAccessible: success
      };
      
      this.logResult(
        'Authentication Endpoints',
        success,
        success ? 'Authentication endpoints accessible' : `Auth endpoints returned ${response.statusCode}`,
        data
      );
      
      return success;
    } catch (error) {
      this.logResult(
        'Authentication Endpoints',
        false,
        `Authentication endpoints test failed: ${error.message}`,
        { error: error.name, code: error.code }
      );
      return false;
    }
  }

  /**
   * Test protected endpoints require authentication
   */
  async testProtectedEndpoints() {
    console.log('\n🧪 Testing Protected Endpoints...');
    
    const protectedEndpoints = [
      '/api/settings/api-keys',
      '/api/portfolio',
      '/api/trading/account',
      '/api/diagnostics/database-connectivity'
    ];
    
    let allProtected = true;
    const results = {};
    
    for (const endpoint of protectedEndpoints) {
      try {
        const response = await this.makeRequest(endpoint);
        const isProtected = response.statusCode === 401;
        
        results[endpoint] = {
          statusCode: response.statusCode,
          isProtected: isProtected,
          hasAuthError: response.body && response.body.error
        };
        
        if (!isProtected) {
          allProtected = false;
        }
      } catch (error) {
        results[endpoint] = {
          error: error.message,
          isProtected: false
        };
        allProtected = false;
      }
    }
    
    this.logResult(
      'Protected Endpoints',
      allProtected,
      allProtected ? 'All protected endpoints require authentication' : 'Some endpoints not properly protected',
      results
    );
    
    return allProtected;
  }

  /**
   * Test error handling
   */
  async testErrorHandling() {
    console.log('\n🧪 Testing Error Handling...');
    
    try {
      const response = await this.makeRequest('/api/nonexistent-endpoint');
      
      const success = response.statusCode === 404;
      const data = {
        statusCode: response.statusCode,
        hasErrorMessage: response.body && response.body.error,
        errorHandledCorrectly: success
      };
      
      this.logResult(
        'Error Handling',
        success,
        success ? 'Error handling working correctly' : `Unexpected error response: ${response.statusCode}`,
        data
      );
      
      return success;
    } catch (error) {
      this.logResult(
        'Error Handling',
        false,
        `Error handling test failed: ${error.message}`,
        { error: error.name, code: error.code }
      );
      return false;
    }
  }

  /**
   * Test response formatting
   */
  async testResponseFormatting() {
    console.log('\n🧪 Testing Response Formatting...');
    
    try {
      const response = await this.makeRequest('/api/health?quick=true');
      
      const success = response.statusCode === 200;
      const hasCorrectFormat = response.body && 
                              typeof response.body === 'object' &&
                              response.body.hasOwnProperty.call(this, 'success');
      
      const data = {
        statusCode: response.statusCode,
        hasBody: !!response.body,
        hasSuccessField: hasCorrectFormat,
        bodyStructure: response.body ? Object.keys(response.body) : null
      };
      
      this.logResult(
        'Response Formatting',
        success && hasCorrectFormat,
        success && hasCorrectFormat ? 'Response formatting consistent' : 'Response formatting issues detected',
        data
      );
      
      return success && hasCorrectFormat;
    } catch (error) {
      this.logResult(
        'Response Formatting',
        false,
        `Response formatting test failed: ${error.message}`,
        { error: error.name, code: error.code }
      );
      return false;
    }
  }

  /**
   * Run all validation tests
   */
  async runAllTests() {
    console.log('🚀 Starting Complete Flow Validation...');
    console.log('='.repeat(80));
    console.log(`Testing API Gateway: ${this.baseUrl}`);
    console.log('='.repeat(80));
    
    // Test API Gateway accessibility
    await this.testApiGateway();
    
    // Test CORS preflight
    await this.testCORSPreflight();
    
    // Test Lambda function
    await this.testLambdaFunction();
    
    // Test database connectivity
    await this.testDatabaseConnectivity();
    
    // Test API key service
    await this.testApiKeyService();
    
    // Test authentication endpoints
    await this.testAuthenticationEndpoints();
    
    // Test protected endpoints
    await this.testProtectedEndpoints();
    
    // Test error handling
    await this.testErrorHandling();
    
    // Test response formatting
    await this.testResponseFormatting();
    
    // Print summary
    console.log('\n' + '='.repeat(80));
    console.log('🏁 Complete Flow Validation Summary:');
    console.log(`✅ Passed: ${this.results.summary.passed}`);
    console.log(`❌ Failed: ${this.results.summary.failed}`);
    console.log(`⚠️  Warnings: ${this.results.summary.warnings}`);
    console.log(`📊 Total Tests: ${this.results.tests.length}`);
    
    const overallSuccess = this.results.summary.failed === 0;
    console.log(`\n🎯 Overall Result: ${overallSuccess ? '✅ PASS' : '❌ FAIL'}`);
    
    if (!overallSuccess) {
      console.log('\n📋 Failed Tests:');
      this.results.tests
        .filter(test => !test.success)
        .forEach(test => {
          console.log(`   ❌ ${test.test}: ${test.message}`);
        });
    }
    
    return this.results;
  }

  /**
   * Generate detailed report
   */
  generateReport() {
    return {
      ...this.results,
      recommendations: this.generateRecommendations()
    };
  }

  /**
   * Generate recommendations based on test results
   */
  generateRecommendations() {
    const recommendations = [];
    
    for (const test of this.results.tests) {
      if (!test.success) {
        switch (test.test) {
          case 'API Gateway Accessibility':
            recommendations.push({
              priority: 'CRITICAL',
              category: 'Infrastructure',
              issue: 'API Gateway not accessible',
              solution: 'Verify API Gateway deployment and domain configuration'
            });
            break;
            
          case 'CORS Preflight':
            recommendations.push({
              priority: 'HIGH',
              category: 'Security',
              issue: 'CORS preflight failing',
              solution: 'Check CORS configuration in API Gateway and Lambda function'
            });
            break;
            
          case 'Lambda Function Response':
            recommendations.push({
              priority: 'CRITICAL',
              category: 'Application',
              issue: 'Lambda function not responding',
              solution: 'Check Lambda function deployment and error logs'
            });
            break;
            
          case 'Database Connectivity':
            recommendations.push({
              priority: 'HIGH',
              category: 'Database',
              issue: 'Database connection issues',
              solution: 'Check database configuration, SSL settings, and network connectivity'
            });
            break;
            
          case 'Protected Endpoints':
            recommendations.push({
              priority: 'CRITICAL',
              category: 'Security',
              issue: 'Some endpoints not properly protected',
              solution: 'Verify authentication middleware is applied to all protected routes'
            });
            break;
        }
      }
    }
    
    return recommendations;
  }
}

// Export for use in other modules
module.exports = CompleteFlowValidator;

// Run validation if called directly
if (require.main === module) {
  const apiUrl = process.argv[2] || process.env.API_GATEWAY_URL;
  
  if (!apiUrl) {
    console.error('❌ Please provide API Gateway URL as argument or API_GATEWAY_URL environment variable');
    console.error('Usage: node validate-complete-flow.js https://your-api-gateway.execute-api.us-east-1.amazonaws.com/dev');
    process.exit(1);
  }
  
  const validator = new CompleteFlowValidator(apiUrl);
  
  validator.runAllTests()
    .then(results => {
      const report = validator.generateReport();
      
      // Save report to file
      const fs = require('fs');
      const reportPath = `complete-flow-validation-report-${Date.now()}.json`;
      fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
      
      console.log(`\n📄 Detailed report saved to: ${reportPath}`);
      
      // Exit with appropriate code
      process.exit(results.summary.failed === 0 ? 0 : 1);
    })
    .catch(error => {
      console.error('Validation execution failed:', error);
      process.exit(1);
    });
}