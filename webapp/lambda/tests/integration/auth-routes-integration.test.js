/**
 * Authentication Routes Integration Tests
 * Tests actual authentication functionality that exists in routes/auth.js
 */

const request = require('supertest');

const { app } = require('../../index');

describe('🔐 Authentication Routes Integration Tests', () => {
  describe('🏥 Auth Health and Status', () => {
    test('GET /api/auth/health - Auth service health', async () => {
      const response = await request(app)
        .get('/api/auth/health')
        .timeout(5000);

      expect([200]).toContain(response.status);
      expect(response.body).toHaveProperty('success', true);
      expect(response.body.data).toHaveProperty('status', 'operational');
      expect(response.body.data).toHaveProperty('service', 'authentication');
      expect(response.body.data).toHaveProperty('timestamp');

      console.log(`✅ Auth health check: ${response.status}`);
    });

    test('GET /api/auth/status - Auth service status', async () => {
      const response = await request(app)
        .get('/api/auth/status')
        .timeout(5000);

      expect([200]).toContain(response.status);
      expect(response.body).toHaveProperty('success', true);
      expect(response.body.data).toHaveProperty('authMethod', 'AWS Cognito');
      expect(response.body.data).toHaveProperty('jwtEnabled', true);
      expect(response.body.data).toHaveProperty('sessionTimeout');
      expect(response.body.data).toHaveProperty('lastCheck');

      console.log(`✅ Auth status check: ${response.status}`);
    });
  });

  describe('🔑 Token Validation', () => {
    test('POST /api/auth/validate - Token validation with valid structure', async () => {
      const validTokenRequest = {
        token: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c'
      };

      const response = await request(app)
        .post('/api/auth/validate')
        .send(validTokenRequest)
        .timeout(5000);

      expect([200]).toContain(response.status);
      expect(response.body).toHaveProperty('success', true);
      expect(response.body.data).toHaveProperty('valid', true);
      expect(response.body.data).toHaveProperty('message');

      console.log(`✅ Token validation (valid structure): ${response.status}`);
    });

    test('POST /api/auth/validate - Token validation without token', async () => {
      const response = await request(app)
        .post('/api/auth/validate')
        .send({}) // No token provided
        .timeout(5000);

      expect([400]).toContain(response.status);
      expect(response.body).toHaveProperty('success', false);
      expect(response.body).toHaveProperty('error', 'Token is required');

      console.log(`✅ Token validation (missing token): ${response.status}`);
    });

    test('POST /api/auth/validate - Token validation with empty token', async () => {
      const emptyTokenRequest = {
        token: ''
      };

      const response = await request(app)
        .post('/api/auth/validate')
        .send(emptyTokenRequest)
        .timeout(5000);

      expect([400]).toContain(response.status);
      expect(response.body).toHaveProperty('success', false);
      expect(response.body).toHaveProperty('error', 'Token is required');

      console.log(`✅ Token validation (empty token): ${response.status}`);
    });

    test('POST /api/auth/validate - Token validation with invalid JSON', async () => {
      const response = await request(app)
        .post('/api/auth/validate')
        .set('Content-Type', 'application/json')
        .send('invalid json')
        .timeout(5000);

      expect([400]).toContain(response.status);

      console.log(`✅ Token validation (invalid JSON): ${response.status}`);
    });
  });

  describe('📝 Request/Response Format', () => {
    test('Auth endpoints return proper JSON format', async () => {
      const endpoints = [
        '/api/auth/health',
        '/api/auth/status'
      ];

      const formatTests = [];

      for (const endpoint of endpoints) {
        const response = await request(app)
          .get(endpoint)
          .timeout(5000);

        formatTests.push({
          endpoint,
          status: response.status,
          hasSuccessField: response.body.hasOwnProperty('success'),
          hasDataField: response.body.hasOwnProperty('data'),
          jsonContentType: response.headers['content-type']?.includes('application/json')
        });
      }

      const allFormattedCorrectly = formatTests.every(test => 
        test.hasSuccessField && 
        test.hasDataField && 
        test.jsonContentType
      );
      expect(allFormattedCorrectly).toBe(true);

      console.log('✅ Auth endpoints return properly formatted JSON');
    });

    test('Auth endpoints include timestamps', async () => {
      const response = await request(app)
        .get('/api/auth/health')
        .timeout(5000);

      expect(response.body.data).toHaveProperty('timestamp');
      
      const timestamp = new Date(response.body.data.timestamp);
      expect(timestamp).toBeInstanceOf(Date);
      expect(timestamp.getTime()).not.toBeNaN();

      console.log('✅ Auth endpoints include valid timestamps');
    });
  });

  describe('🛡️ Security Headers', () => {
    test('Auth endpoints include security headers', async () => {
      const response = await request(app)
        .get('/api/auth/health')
        .timeout(5000);

      expect(response.headers['x-content-type-options']).toBeDefined();
      expect(response.headers['x-frame-options']).toBeDefined();
      expect(response.headers['x-xss-protection']).toBeDefined();

      console.log('✅ Auth endpoints include security headers');
    });

    test('Auth endpoints remove sensitive headers', async () => {
      const response = await request(app)
        .get('/api/auth/health')
        .timeout(5000);

      expect(response.headers['x-powered-by']).toBeUndefined();
      expect(response.headers['server']).toBeUndefined();

      console.log('✅ Auth endpoints remove sensitive headers');
    });
  });

  describe('🌐 CORS Support', () => {
    test('Auth endpoints support CORS', async () => {
      const response = await request(app)
        .get('/api/auth/health')
        .set('Origin', 'https://d1zb7knau41vl9.cloudfront.net')
        .timeout(5000);

      expect(response.headers['access-control-allow-origin']).toBeDefined();
      expect(response.headers['access-control-allow-credentials']).toBeDefined();

      console.log('✅ Auth endpoints support CORS');
    });

    test('OPTIONS requests handled for auth endpoints', async () => {
      const response = await request(app)
        .options('/api/auth/health')
        .set('Origin', 'https://d1zb7knau41vl9.cloudfront.net')
        .timeout(5000);

      expect([200, 204]).toContain(response.status);
      expect(response.headers['access-control-allow-methods']).toBeDefined();

      console.log(`✅ AUTH OPTIONS request: ${response.status}`);
    });
  });

  describe('⚡ Performance Testing', () => {
    test('Auth endpoints respond quickly', async () => {
      const performanceTests = [];
      
      const endpoints = [
        { path: '/api/auth/health', timeout: 5000 },
        { path: '/api/auth/status', timeout: 5000 }
      ];

      for (const endpoint of endpoints) {
        const startTime = Date.now();
        
        const response = await request(app)
          .get(endpoint.path)
          .timeout(endpoint.timeout);

        const responseTime = Date.now() - startTime;
        
        performanceTests.push({
          endpoint: endpoint.path,
          responseTime,
          status: response.status,
          withinTimeout: responseTime < endpoint.timeout
        });
      }

      const allWithinTimeout = performanceTests.every(test => test.withinTimeout);
      expect(allWithinTimeout).toBe(true);

      const avgResponseTime = performanceTests.reduce((sum, test) => sum + test.responseTime, 0) / performanceTests.length;
      console.log(`⚡ Average auth response time: ${avgResponseTime.toFixed(0)}ms`);
      
      // Auth endpoints should be very fast
      expect(avgResponseTime).toBeLessThan(1000);
    });

    test('Token validation performance', async () => {
      const validationTests = [];
      
      // Test multiple token validations
      for (let i = 0; i < 5; i++) {
        const startTime = Date.now();
        
        const response = await request(app)
          .post('/api/auth/validate')
          .send({
            token: `test-token-${i}`
          })
          .timeout(5000);

        const responseTime = Date.now() - startTime;
        
        validationTests.push({
          test: `validation_${i}`,
          responseTime,
          status: response.status
        });
      }

      const avgValidationTime = validationTests.reduce((sum, test) => sum + test.responseTime, 0) / validationTests.length;
      console.log(`⚡ Average token validation time: ${avgValidationTime.toFixed(0)}ms`);
      
      // Token validation should be fast
      expect(avgValidationTime).toBeLessThan(500);
    });
  });

  describe('🔄 Error Handling', () => {
    test('Invalid HTTP methods handled', async () => {
      const response = await request(app)
        .patch('/api/auth/health')
        .timeout(5000);

      expect([404, 405]).toContain(response.status);

      console.log(`✅ Invalid HTTP method handling: ${response.status}`);
    });

    test('Malformed requests handled gracefully', async () => {
      const malformedTests = [];

      // Test with invalid content type
      const invalidContentType = await request(app)
        .post('/api/auth/validate')
        .set('Content-Type', 'text/plain')
        .send('not json')
        .timeout(5000);

      malformedTests.push({
        test: 'invalid_content_type',
        status: invalidContentType.status,
        handled: [400, 415].includes(invalidContentType.status)
      });

      // Test with oversized payload
      const largePayload = {
        token: 'x'.repeat(10000) // Very large token
      };

      const oversizedRequest = await request(app)
        .post('/api/auth/validate')
        .send(largePayload)
        .timeout(5000);

      malformedTests.push({
        test: 'oversized_payload',
        status: oversizedRequest.status,
        handled: [200, 400, 413].includes(oversizedRequest.status)
      });

      const allHandled = malformedTests.every(test => test.handled);
      expect(allHandled).toBe(true);

      console.log('✅ Malformed requests handled gracefully');
    });
  });

  describe('🔄 Integration Summary', () => {
    test('Authentication integration test summary', async () => {
      const authResults = [];
      
      console.log('🔐 Running authentication integration summary...');

      // Test 1: Service health
      const healthTest = await request(app)
        .get('/api/auth/health')
        .timeout(5000);
      
      authResults.push({
        test: 'service_health',
        success: healthTest.status === 200 && healthTest.body.success === true
      });

      // Test 2: Service status
      const statusTest = await request(app)
        .get('/api/auth/status')
        .timeout(5000);
      
      authResults.push({
        test: 'service_status',
        success: statusTest.status === 200 && statusTest.body.success === true
      });

      // Test 3: Token validation
      const validationTest = await request(app)
        .post('/api/auth/validate')
        .send({ token: 'test-token' })
        .timeout(5000);
      
      authResults.push({
        test: 'token_validation',
        success: validationTest.status === 200 && validationTest.body.success === true
      });

      // Test 4: Error handling
      const errorTest = await request(app)
        .post('/api/auth/validate')
        .send({}) // Missing token
        .timeout(5000);
      
      authResults.push({
        test: 'error_handling',
        success: errorTest.status === 400 && errorTest.body.success === false
      });

      // Test 5: Security headers
      const securityTest = await request(app)
        .get('/api/auth/health')
        .timeout(5000);
      
      authResults.push({
        test: 'security_headers',
        success: securityTest.headers['x-content-type-options'] !== undefined
      });

      const successfulTests = authResults.filter(t => t.success).length;
      expect(successfulTests).toBe(authResults.length);
      
      console.log('✅ Authentication integration tests completed:', authResults.map(t => t.test).join(', '));
      console.log(`🎯 Authentication success rate: ${successfulTests}/${authResults.length} (${(successfulTests/authResults.length*100).toFixed(1)}%)`);
    });
  });
});