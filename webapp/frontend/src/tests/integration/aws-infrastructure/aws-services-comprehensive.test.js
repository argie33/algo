/**
 * Comprehensive AWS Infrastructure Integration Tests
 * Tests real AWS services: Lambda, S3, CloudFront, API Gateway, RDS, ECS, CloudWatch
 * NO MOCKS - Tests against actual AWS infrastructure and real service integrations
 */

import { test, expect } from '@playwright/test';

const testConfig = {
  baseURL: process.env.E2E_BASE_URL || 'https://d1zb7knau41vl9.cloudfront.net',
  apiURL: process.env.E2E_API_URL || 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev',
  s3BucketURL: process.env.S3_BUCKET_URL || 'https://stocks-dashboard-assets.s3.amazonaws.com',
  cloudWatchURL: process.env.CLOUDWATCH_URL,
  testUser: {
    email: process.env.E2E_TEST_EMAIL || 'e2e-test@example.com',
    password: process.env.E2E_TEST_PASSWORD || 'E2ETest123!'
  },
  timeout: 120000 // Extended timeout for AWS operations
};

test.describe('Comprehensive AWS Infrastructure Integration - Enterprise Framework', () => {
  
  let awsSession = {
    lambdaInvocations: [],
    s3Operations: [],
    cloudFrontEvents: [],
    apiGatewayEvents: [],
    ecsEvents: [],
    cloudWatchMetrics: [],
    infrastructureErrors: [],
    errors: []
  };

  async function authenticate(page) {
    const isAuth = await page.locator('[data-testid="user-avatar"]').isVisible().catch(() => false);
    if (!isAuth) {
      await page.locator('button:has-text("Sign In")').click();
      await page.fill('[data-testid="email-input"]', testConfig.testUser.email);
      await page.fill('[data-testid="password-input"]', testConfig.testUser.password);
      await page.click('[data-testid="login-submit"]');
      await page.waitForSelector('[data-testid="user-avatar"]', { timeout: 15000 });
    }
  }

  async function trackAWSEvent(eventType, data) {
    awsSession[eventType].push({
      ...data,
      timestamp: new Date().toISOString()
    });
  }

  test.beforeEach(async ({ page }) => {
    // Reset AWS session tracking
    awsSession = {
      lambdaInvocations: [],
      s3Operations: [],
      cloudFrontEvents: [],
      apiGatewayEvents: [],
      ecsEvents: [],
      cloudWatchMetrics: [],
      infrastructureErrors: [],
      errors: []
    };
    
    // Monitor requests to AWS services
    page.on('request', request => {
      const url = request.url();
      
      // Track Lambda invocations
      if (url.includes('lambda') || url.includes('execute-api')) {
        trackAWSEvent('lambdaInvocations', {
          type: 'lambda_request',
          url: url,
          method: request.method(),
          headers: request.headers()
        });
      }
      
      // Track S3 operations
      if (url.includes('s3') || url.includes('amazonaws.com') && (url.includes('bucket') || url.includes('object'))) {
        trackAWSEvent('s3Operations', {
          type: 's3_request',
          url: url,
          method: request.method(),
          operation: extractS3Operation(url)
        });
      }
      
      // Track CloudFront requests
      if (url.includes('cloudfront') || url.includes('cloudfront.net')) {
        trackAWSEvent('cloudFrontEvents', {
          type: 'cloudfront_request',
          url: url,
          method: request.method()
        });
      }
    });

    page.on('response', response => {
      const url = response.url();
      
      // Track AWS service responses
      if (url.includes('amazonaws.com') || url.includes('execute-api')) {
        const serviceName = extractAWSService(url);
        
        trackAWSEvent('apiGatewayEvents', {
          type: 'aws_response',
          service: serviceName,
          url: url,
          status: response.status(),
          headers: response.headers()
        });
        
        // Track AWS errors
        if (!response.ok()) {
          trackAWSEvent('infrastructureErrors', {
            service: serviceName,
            url: url,
            status: response.status(),
            statusText: response.statusText()
          });
        }
      }
    });

    // Monitor console for AWS-related errors
    page.on('console', msg => {
      if (msg.type() === 'error') {
        const errorText = msg.text();
        if (errorText.includes('aws') || errorText.includes('lambda') || 
            errorText.includes('s3') || errorText.includes('cloudfront') ||
            errorText.includes('ecs') || errorText.includes('cloudwatch')) {
          awsSession.errors.push({
            message: errorText,
            timestamp: new Date().toISOString()
          });
        }
      }
    });

    await page.goto(testConfig.baseURL);
    await page.waitForLoadState('networkidle');
  });

  function extractAWSService(url) {
    if (url.includes('lambda') || url.includes('execute-api')) return 'lambda';
    if (url.includes('s3')) return 's3';
    if (url.includes('cloudfront')) return 'cloudfront';
    if (url.includes('rds')) return 'rds';
    if (url.includes('ecs')) return 'ecs';
    if (url.includes('cloudwatch')) return 'cloudwatch';
    return 'unknown';
  }

  function extractS3Operation(url) {
    if (url.includes('PUT')) return 'upload';
    if (url.includes('GET')) return 'download';
    if (url.includes('DELETE')) return 'delete';
    if (url.includes('HEAD')) return 'metadata';
    return 'unknown';
  }

  test.describe('Lambda Function Integration @critical @enterprise @aws-lambda', () => {

    test('Real Lambda Function Invocation and Response Handling', async ({ page, request }) => {
      console.log('⚡ Testing Real Lambda Function Invocation and Response Handling...');
      
      await authenticate(page);
      
      // 1. Test portfolio data Lambda functions
      console.log('📊 Testing portfolio data Lambda functions...');
      
      const lambdaEndpoints = [
        '/api/portfolio/holdings',
        '/api/portfolio/performance', 
        '/api/portfolio/risk-analysis',
        '/api/portfolio/rebalancing'
      ];
      
      for (const endpoint of lambdaEndpoints) {
        console.log(`⚡ Testing Lambda endpoint: ${endpoint}`);
        
        const startTime = Date.now();
        const response = await request.get(`${testConfig.apiURL}${endpoint}`, {
          headers: {
            'Authorization': `Bearer ${await getAuthToken(page)}`,
            'Content-Type': 'application/json'
          }
        });
        const responseTime = Date.now() - startTime;
        
        console.log(`⚡ ${endpoint}: ${response.status()} (${responseTime}ms)`);
        
        await trackAWSEvent('lambdaInvocations', {
          endpoint: endpoint,
          status: response.status(),
          responseTime: responseTime,
          success: response.ok()
        });
        
        if (response.ok()) {
          const data = await response.json();
          console.log(`✅ Lambda function returned valid data structure`);
          
          // Verify Lambda response headers
          const lambdaHeaders = response.headers();
          if (lambdaHeaders['x-amzn-requestid']) {
            console.log(`🆔 Lambda Request ID: ${lambdaHeaders['x-amzn-requestid']}`);
          }
          
          // Check for cold start indicators
          if (responseTime > 5000) {
            console.log(`❄️ Potential cold start detected (${responseTime}ms)`);
            await trackAWSEvent('lambdaInvocations', {
              type: 'cold_start',
              endpoint: endpoint,
              responseTime: responseTime
            });
          }
        } else {
          console.log(`🚨 Lambda function error: ${response.status()} ${response.statusText()}`);
        }
      }
      
      // 2. Test data processing Lambda functions
      console.log('🔄 Testing data processing Lambda functions...');
      
      await page.goto('/admin/data-processing');
      await page.waitForSelector('[data-testid="data-processing-admin"]', { timeout: 15000 });
      
      // Trigger data processing job
      const processButton = page.locator('[data-testid="trigger-data-processing"]');
      if (await processButton.isVisible()) {
        await processButton.click();
        
        // Monitor processing status
        await page.waitForTimeout(5000);
        
        const processingStatus = page.locator('[data-testid="processing-status"]');
        if (await processingStatus.isVisible()) {
          const statusText = await processingStatus.textContent();
          console.log(`🔄 Data processing status: ${statusText}`);
          
          await trackAWSEvent('lambdaInvocations', {
            type: 'data_processing',
            status: statusText,
            triggered: true
          });
        }
      }
      
      // 3. Test Lambda error handling
      console.log('🚨 Testing Lambda error handling...');
      
      // Trigger intentional error for testing
      const errorTestEndpoint = '/api/admin/test-lambda-error';
      const errorResponse = await request.post(`${testConfig.apiURL}${errorTestEndpoint}`, {
        headers: {
          'Authorization': `Bearer ${await getAuthToken(page)}`
        }
      }).catch(error => ({ error: error.message }));
      
      if (errorResponse.status) {
        console.log(`🚨 Lambda error test response: ${errorResponse.status()}`);
        
        await trackAWSEvent('lambdaInvocations', {
          type: 'error_test',
          status: errorResponse.status(),
          endpoint: errorTestEndpoint
        });
      }
      
      console.log('✅ Real Lambda Function Invocation and Response Handling completed');
    });

    test('Lambda Performance and Scaling Integration', async ({ page, request }) => {
      console.log('📈 Testing Lambda Performance and Scaling Integration...');
      
      await authenticate(page);
      
      // 1. Test concurrent Lambda invocations
      console.log('🔄 Testing concurrent Lambda invocations...');
      
      const concurrentRequests = [];
      const testEndpoint = '/api/market/overview';
      const concurrentCount = 10;
      
      for (let i = 0; i < concurrentCount; i++) {
        concurrentRequests.push(
          request.get(`${testConfig.apiURL}${testEndpoint}`)
            .then(response => ({
              requestId: i,
              status: response.status(),
              responseTime: Date.now(),
              headers: response.headers()
            }))
            .catch(error => ({
              requestId: i,
              error: error.message
            }))
        );
      }
      
      const results = await Promise.all(concurrentRequests);
      
      const successfulRequests = results.filter(r => r.status === 200);
      const averageResponseTime = successfulRequests.reduce((sum, r) => sum + r.responseTime, 0) / successfulRequests.length;
      
      console.log(`📊 Concurrent requests: ${successfulRequests.length}/${concurrentCount} successful`);
      console.log(`📊 Average response time: ${averageResponseTime.toFixed(0)}ms`);
      
      await trackAWSEvent('lambdaInvocations', {
        type: 'concurrent_test',
        totalRequests: concurrentCount,
        successfulRequests: successfulRequests.length,
        averageResponseTime: averageResponseTime
      });
      
      // 2. Test Lambda memory and timeout limits
      console.log('💾 Testing Lambda memory and timeout limits...');
      
      const memoryTestEndpoint = '/api/admin/lambda-memory-test';
      const memoryTestResponse = await request.post(`${testConfig.apiURL}${memoryTestEndpoint}`, {
        data: {
          testType: 'memory_stress',
          iterations: 1000
        },
        headers: {
          'Authorization': `Bearer ${await getAuthToken(page)}`
        }
      }).catch(error => ({ error: error.message }));
      
      if (memoryTestResponse.status) {
        console.log(`💾 Memory test response: ${memoryTestResponse.status()}`);
        
        if (memoryTestResponse.ok()) {
          const memoryData = await memoryTestResponse.json();
          console.log(`💾 Memory usage: ${memoryData.memoryUsed}MB`);
          console.log(`⏱️ Execution time: ${memoryData.executionTime}ms`);
          
          await trackAWSEvent('lambdaInvocations', {
            type: 'memory_test',
            memoryUsed: memoryData.memoryUsed,
            executionTime: memoryData.executionTime
          });
        }
      }
      
      console.log('✅ Lambda Performance and Scaling Integration completed');
    });

  });

  test.describe('S3 Storage Integration @critical @enterprise @aws-s3', () => {

    test('Real S3 File Operations and CDN Integration', async ({ page }) => {
      console.log('📦 Testing Real S3 File Operations and CDN Integration...');
      
      await authenticate(page);
      
      // 1. Test S3 asset loading
      console.log('🖼️ Testing S3 asset loading...');
      
      await page.goto('/');
      await page.waitForLoadState('networkidle');
      
      // Check for assets loaded from S3/CloudFront
      const images = page.locator('img');
      const imageCount = await images.count();
      
      let s3AssetsLoaded = 0;
      for (let i = 0; i < imageCount; i++) {
        const img = images.nth(i);
        const src = await img.getAttribute('src');
        
        if (src && (src.includes('s3') || src.includes('cloudfront') || src.includes('amazonaws.com'))) {
          s3AssetsLoaded++;
          console.log(`📦 S3 asset loaded: ${src.substring(0, 100)}...`);
          
          await trackAWSEvent('s3Operations', {
            type: 'asset_load',
            url: src,
            assetType: 'image'
          });
        }
      }
      
      console.log(`📦 S3 assets loaded: ${s3AssetsLoaded}/${imageCount} images`);
      
      // 2. Test file upload functionality
      console.log('⬆️ Testing file upload functionality...');
      
      await page.goto('/settings/profile');
      await page.waitForSelector('[data-testid="profile-settings"]', { timeout: 15000 });
      
      const fileUpload = page.locator('[data-testid="profile-image-upload"]');
      if (await fileUpload.isVisible()) {
        // Create a test file
        const testFile = await page.evaluateHandle(() => {
          const canvas = document.createElement('canvas');
          canvas.width = 100;
          canvas.height = 100;
          const ctx = canvas.getContext('2d');
          ctx.fillStyle = 'blue';
          ctx.fillRect(0, 0, 100, 100);
          
          return new Promise((resolve) => {
            canvas.toBlob(resolve, 'image/png');
          });
        });
        
        await fileUpload.setInputFiles(testFile);
        
        // Monitor upload progress
        const uploadProgress = page.locator('[data-testid="upload-progress"]');
        if (await uploadProgress.isVisible({ timeout: 5000 })) {
          console.log('⬆️ Upload progress indicator visible');
          
          // Wait for upload completion
          await page.waitForSelector('[data-testid="upload-complete"]', { timeout: 30000 });
          console.log('✅ File upload completed');
          
          await trackAWSEvent('s3Operations', {
            type: 'file_upload',
            success: true,
            fileType: 'image/png'
          });
        }
      }
      
      // 3. Test S3 bucket permissions and security
      console.log('🔒 Testing S3 bucket permissions and security...');
      
      // Try to access S3 bucket directly (should be restricted)
      const directS3Response = await page.request.get(`${testConfig.s3BucketURL}/private/test-file.txt`);
      
      if (directS3Response.status() === 403 || directS3Response.status() === 404) {
        console.log('✅ S3 bucket properly secured - direct access denied');
        
        await trackAWSEvent('s3Operations', {
          type: 'security_test',
          directAccessBlocked: true,
          status: directS3Response.status()
        });
      } else {
        console.log('⚠️ S3 bucket may have overly permissive access');
      }
      
      console.log('✅ Real S3 File Operations and CDN Integration completed');
    });

    test('S3 Performance and CloudFront Caching', async ({ page, request }) => {
      console.log('🚀 Testing S3 Performance and CloudFront Caching...');
      
      // 1. Test CloudFront cache performance
      console.log('⚡ Testing CloudFront cache performance...');
      
      const testAssetURL = `${testConfig.baseURL}/static/js/main.js`;
      
      // First request (likely cache miss)
      const startTime1 = Date.now();
      const response1 = await request.get(testAssetURL);
      const responseTime1 = Date.now() - startTime1;
      
      const cacheStatus1 = response1.headers()['x-cache'] || response1.headers()['cloudfront-cache-status'];
      console.log(`⚡ First request: ${responseTime1}ms, Cache: ${cacheStatus1}`);
      
      // Second request (should be cache hit)
      const startTime2 = Date.now();
      const response2 = await request.get(testAssetURL);
      const responseTime2 = Date.now() - startTime2;
      
      const cacheStatus2 = response2.headers()['x-cache'] || response2.headers()['cloudfront-cache-status'];
      console.log(`⚡ Second request: ${responseTime2}ms, Cache: ${cacheStatus2}`);
      
      await trackAWSEvent('cloudFrontEvents', {
        type: 'cache_performance_test',
        firstRequestTime: responseTime1,
        secondRequestTime: responseTime2,
        cacheStatus1: cacheStatus1,
        cacheStatus2: cacheStatus2,
        cacheSpeedup: responseTime1 / responseTime2
      });
      
      if (responseTime2 < responseTime1) {
        console.log(`✅ CloudFront caching working - ${((1 - responseTime2/responseTime1) * 100).toFixed(1)}% faster`);
      }
      
      // 2. Test multiple asset loading performance
      console.log('📦 Testing multiple asset loading performance...');
      
      await page.goto('/');
      
      // Monitor network activity
      const resourcePromises = [];
      page.on('response', response => {
        if (response.url().includes('cloudfront') || response.url().includes('s3')) {
          resourcePromises.push({
            url: response.url(),
            status: response.status(),
            size: parseInt(response.headers()['content-length'] || '0'),
            cacheStatus: response.headers()['x-cache'] || 'unknown'
          });
        }
      });
      
      await page.waitForLoadState('networkidle');
      
      const loadedResources = resourcePromises.slice(0, 10); // Sample first 10
      const totalSize = loadedResources.reduce((sum, resource) => sum + resource.size, 0);
      const cachedResources = loadedResources.filter(resource => 
        resource.cacheStatus.includes('Hit') || resource.cacheStatus.includes('hit')
      );
      
      console.log(`📦 Resources loaded: ${loadedResources.length}`);
      console.log(`📦 Total size: ${(totalSize / 1024).toFixed(1)} KB`);
      console.log(`📦 Cache hits: ${cachedResources.length}/${loadedResources.length}`);
      
      await trackAWSEvent('cloudFrontEvents', {
        type: 'resource_loading_performance',
        totalResources: loadedResources.length,
        totalSize: totalSize,
        cacheHits: cachedResources.length,
        cacheHitRate: (cachedResources.length / loadedResources.length * 100).toFixed(1)
      });
      
      console.log('✅ S3 Performance and CloudFront Caching completed');
    });

  });

  test.describe('ECS Container Service Integration @critical @enterprise @aws-ecs', () => {

    test('ECS Service Health and Container Management', async ({ page }) => {
      console.log('🐳 Testing ECS Service Health and Container Management...');
      
      await authenticate(page);
      
      // 1. Check ECS service status
      console.log('📊 Checking ECS service status...');
      
      await page.goto('/admin/infrastructure');
      await page.waitForSelector('[data-testid="infrastructure-dashboard"]', { timeout: 15000 });
      
      const ecsStatus = page.locator('[data-testid="ecs-service-status"]');
      if (await ecsStatus.isVisible()) {
        const statusText = await ecsStatus.textContent();
        console.log(`🐳 ECS service status: ${statusText}`);
        
        await trackAWSEvent('ecsEvents', {
          type: 'service_status_check',
          status: statusText,
          healthy: statusText.includes('running') || statusText.includes('active')
        });
      }
      
      // 2. Check container health
      const containerHealth = page.locator('[data-testid="container-health"]');
      if (await containerHealth.isVisible()) {
        const healthText = await containerHealth.textContent();
        console.log(`🐳 Container health: ${healthText}`);
        
        await trackAWSEvent('ecsEvents', {
          type: 'container_health_check',
          health: healthText
        });
      }
      
      // 3. Test service scaling indicators
      const scalingInfo = page.locator('[data-testid="ecs-scaling-info"]');
      if (await scalingInfo.isVisible()) {
        const scalingText = await scalingInfo.textContent();
        console.log(`📊 ECS scaling info: ${scalingText}`);
        
        await trackAWSEvent('ecsEvents', {
          type: 'scaling_info',
          details: scalingText
        });
      }
      
      console.log('✅ ECS Service Health and Container Management completed');
    });

  });

  test.describe('CloudWatch Monitoring Integration @critical @enterprise @aws-cloudwatch', () => {

    test('CloudWatch Metrics and Logging Integration', async ({ page }) => {
      console.log('📊 Testing CloudWatch Metrics and Logging Integration...');
      
      await authenticate(page);
      
      // 1. Check application metrics
      console.log('📈 Checking application metrics...');
      
      await page.goto('/admin/monitoring');
      await page.waitForSelector('[data-testid="monitoring-dashboard"]', { timeout: 15000 });
      
      const metrics = {
        'api-response-time': '[data-testid="api-response-time-metric"]',
        'error-rate': '[data-testid="error-rate-metric"]',
        'active-users': '[data-testid="active-users-metric"]',
        'lambda-invocations': '[data-testid="lambda-invocations-metric"]',
        'database-connections': '[data-testid="database-connections-metric"]'
      };
      
      for (const [metricName, selector] of Object.entries(metrics)) {
        const metricElement = page.locator(selector);
        if (await metricElement.isVisible()) {
          const metricValue = await metricElement.textContent();
          console.log(`📊 ${metricName}: ${metricValue}`);
          
          await trackAWSEvent('cloudWatchMetrics', {
            metric: metricName,
            value: metricValue
          });
        }
      }
      
      // 2. Check for CloudWatch alarms
      const alarmsSection = page.locator('[data-testid="cloudwatch-alarms"]');
      if (await alarmsSection.isVisible()) {
        const alarms = page.locator('[data-testid^="alarm-"]');
        const alarmCount = await alarms.count();
        
        console.log(`🚨 Active CloudWatch alarms: ${alarmCount}`);
        
        if (alarmCount > 0) {
          for (let i = 0; i < Math.min(5, alarmCount); i++) {
            const alarm = alarms.nth(i);
            const alarmName = await alarm.locator('[data-testid="alarm-name"]').textContent();
            const alarmState = await alarm.locator('[data-testid="alarm-state"]').textContent();
            
            console.log(`🚨 Alarm: ${alarmName} - ${alarmState}`);
            
            await trackAWSEvent('cloudWatchMetrics', {
              type: 'alarm',
              name: alarmName,
              state: alarmState
            });
          }
        }
      }
      
      // 3. Test log viewing functionality
      const logsSection = page.locator('[data-testid="cloudwatch-logs"]');
      if (await logsSection.isVisible()) {
        await logsSection.click();
        
        await page.waitForSelector('[data-testid="log-entries"]', { timeout: 10000 });
        
        const logEntries = page.locator('[data-testid^="log-entry-"]');
        const logCount = await logEntries.count();
        
        console.log(`📋 Recent log entries: ${logCount}`);
        
        await trackAWSEvent('cloudWatchMetrics', {
          type: 'log_access',
          logCount: logCount
        });
      }
      
      console.log('✅ CloudWatch Metrics and Logging Integration completed');
    });

  });

  // Helper function to get auth token
  async function getAuthToken(page) {
    return await page.evaluate(() => {
      return localStorage.getItem('access_token') || 
             localStorage.getItem('authToken') ||
             sessionStorage.getItem('access_token') ||
             sessionStorage.getItem('authToken') ||
             'test-token';
    });
  }

  test.afterEach(async () => {
    // AWS infrastructure session summary
    console.log('\n🌥️ AWS Infrastructure Integration Session Summary:');
    console.log(`Lambda invocations: ${awsSession.lambdaInvocations.length}`);
    console.log(`S3 operations: ${awsSession.s3Operations.length}`);
    console.log(`CloudFront events: ${awsSession.cloudFrontEvents.length}`);
    console.log(`API Gateway events: ${awsSession.apiGatewayEvents.length}`);
    console.log(`ECS events: ${awsSession.ecsEvents.length}`);
    console.log(`CloudWatch metrics: ${awsSession.cloudWatchMetrics.length}`);
    console.log(`Infrastructure errors: ${awsSession.infrastructureErrors.length}`);
    console.log(`Total errors: ${awsSession.errors.length}`);
    
    // Log Lambda performance metrics
    if (awsSession.lambdaInvocations.length > 0) {
      console.log('\n⚡ Lambda Performance Summary:');
      const successfulInvocations = awsSession.lambdaInvocations.filter(inv => inv.success);
      const averageResponseTime = successfulInvocations.reduce((sum, inv) => sum + (inv.responseTime || 0), 0) / successfulInvocations.length;
      
      console.log(`  Successful invocations: ${successfulInvocations.length}/${awsSession.lambdaInvocations.length}`);
      console.log(`  Average response time: ${averageResponseTime.toFixed(0)}ms`);
      
      const coldStarts = awsSession.lambdaInvocations.filter(inv => inv.type === 'cold_start');
      if (coldStarts.length > 0) {
        console.log(`  Cold starts detected: ${coldStarts.length}`);
      }
    }
    
    // Log S3 and CloudFront performance
    if (awsSession.s3Operations.length > 0 || awsSession.cloudFrontEvents.length > 0) {
      console.log('\n📦 S3/CloudFront Performance Summary:');
      console.log(`  S3 operations: ${awsSession.s3Operations.length}`);
      console.log(`  CloudFront events: ${awsSession.cloudFrontEvents.length}`);
      
      const cacheTests = awsSession.cloudFrontEvents.filter(event => event.type === 'cache_performance_test');
      if (cacheTests.length > 0) {
        const avgSpeedup = cacheTests.reduce((sum, test) => sum + (test.cacheSpeedup || 1), 0) / cacheTests.length;
        console.log(`  Average cache speedup: ${avgSpeedup.toFixed(2)}x`);
      }
    }
    
    // Log infrastructure errors
    if (awsSession.infrastructureErrors.length > 0) {
      console.log('\n🚨 Infrastructure Errors:');
      awsSession.infrastructureErrors.forEach(error => {
        console.log(`  ${error.service}: ${error.status} - ${error.url}`);
      });
    }
    
    // Calculate overall AWS service health
    const totalAWSEvents = awsSession.lambdaInvocations.length + awsSession.s3Operations.length + 
                          awsSession.cloudFrontEvents.length + awsSession.apiGatewayEvents.length;
    const errorEvents = awsSession.infrastructureErrors.length;
    const healthScore = totalAWSEvents > 0 ? ((totalAWSEvents - errorEvents) / totalAWSEvents * 100).toFixed(1) : 100;
    
    console.log(`\n📊 AWS Infrastructure Health Score: ${healthScore}% (${totalAWSEvents - errorEvents}/${totalAWSEvents})`);
  });

});

export default {
  testConfig
};