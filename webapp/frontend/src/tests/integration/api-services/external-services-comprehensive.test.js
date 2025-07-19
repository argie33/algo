/**
 * Comprehensive External Services and API Integration Tests
 * Tests real API key management, external service connections, and service reliability
 * Focuses on known problem areas: Alpaca API, Polygon, Finnhub, API key validation
 * NO MOCKS - Tests against actual external services and real API integrations
 */

import { test, expect } from '@playwright/test';

const testConfig = {
  baseURL: process.env.E2E_BASE_URL || 'https://d1zb7knau41vl9.cloudfront.net',
  apiURL: process.env.E2E_API_URL || 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev',
  testUser: {
    email: process.env.E2E_TEST_EMAIL || 'e2e-test@example.com',
    password: process.env.E2E_TEST_PASSWORD || 'E2ETest123!'
  },
  // Test API keys (use sandbox/demo keys)
  testApiKeys: {
    alpaca: {
      key: process.env.TEST_ALPACA_KEY || 'PKTest123',
      secret: process.env.TEST_ALPACA_SECRET || 'SKTest456',
      invalidKey: 'INVALID_KEY_123'
    },
    polygon: {
      key: process.env.TEST_POLYGON_KEY || 'PolygonTest789',
      invalidKey: 'INVALID_POLYGON_123'
    },
    finnhub: {
      key: process.env.TEST_FINNHUB_KEY || 'FinnhubTest456',
      invalidKey: 'INVALID_FINNHUB_789'
    }
  },
  timeout: 60000
};

test.describe('Comprehensive External Services and API Integration - Enterprise Framework', () => {
  
  let servicesSession = {
    apiKeyValidations: [],
    serviceConnections: [],
    dataQuality: [],
    rateLimits: [],
    serviceErrors: [],
    fallbackEvents: [],
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

  async function trackServiceEvent(eventType, data) {
    servicesSession[eventType].push({
      ...data,
      timestamp: new Date().toISOString()
    });
  }

  test.beforeEach(async ({ page }) => {
    // Reset services session tracking
    servicesSession = {
      apiKeyValidations: [],
      serviceConnections: [],
      dataQuality: [],
      rateLimits: [],
      serviceErrors: [],
      fallbackEvents: [],
      errors: []
    };
    
    // Monitor network requests to external services
    page.on('request', request => {
      const url = request.url();
      if (url.includes('alpaca') || url.includes('polygon') || url.includes('finnhub') || 
          url.includes('iex') || url.includes('yahoo') || url.includes('external-api')) {
        trackServiceEvent('serviceConnections', {
          type: 'request_start',
          service: extractServiceName(url),
          url: url,
          method: request.method(),
          startTime: Date.now()
        });
      }
    });

    page.on('response', response => {
      const url = response.url();
      if (url.includes('alpaca') || url.includes('polygon') || url.includes('finnhub') || 
          url.includes('iex') || url.includes('yahoo') || url.includes('external-api')) {
        trackServiceEvent('serviceConnections', {
          type: 'response_received',
          service: extractServiceName(url),
          url: url,
          status: response.status(),
          responseTime: Date.now()
        });
        
        // Track rate limiting
        if (response.status() === 429) {
          trackServiceEvent('rateLimits', {
            service: extractServiceName(url),
            url: url,
            headers: response.headers()
          });
        }
      }
    });

    // Monitor console for API-related errors
    page.on('console', msg => {
      if (msg.type() === 'error') {
        const errorText = msg.text();
        if (errorText.includes('api') || errorText.includes('alpaca') || 
            errorText.includes('polygon') || errorText.includes('finnhub') ||
            errorText.includes('rate limit') || errorText.includes('unauthorized')) {
          servicesSession.errors.push({
            message: errorText,
            timestamp: new Date().toISOString()
          });
        }
      }
    });

    await page.goto(testConfig.baseURL);
    await page.waitForLoadState('networkidle');
  });

  function extractServiceName(url) {
    if (url.includes('alpaca')) return 'alpaca';
    if (url.includes('polygon')) return 'polygon';
    if (url.includes('finnhub')) return 'finnhub';
    if (url.includes('iex')) return 'iex';
    if (url.includes('yahoo')) return 'yahoo';
    return 'unknown';
  }

  test.describe('API Key Management and Validation @critical @enterprise @api-keys', () => {

    test('Real API Key Validation and Management', async ({ page }) => {
      console.log('🔑 Testing Real API Key Validation and Management...');
      
      await authenticate(page);
      
      // 1. Navigate to API key management
      await page.goto('/settings/api-keys');
      await page.waitForSelector('[data-testid="api-keys-settings"]', { timeout: 15000 });
      
      // 2. Test Alpaca API key validation
      console.log('📊 Testing Alpaca API key validation...');
      
      const alpacaSection = page.locator('[data-testid="alpaca-api-section"]');
      if (await alpacaSection.isVisible()) {
        // Test with invalid key first
        await page.fill('[data-testid="alpaca-api-key"]', testConfig.testApiKeys.alpaca.invalidKey);
        await page.fill('[data-testid="alpaca-api-secret"]', 'invalid-secret');
        
        await page.click('[data-testid="test-alpaca-connection"]');
        
        // Wait for validation result
        await page.waitForTimeout(8000);
        
        const alpacaError = page.locator('[data-testid="alpaca-validation-error"]');
        if (await alpacaError.isVisible()) {
          const errorText = await alpacaError.textContent();
          console.log(`🚨 Alpaca invalid key error: ${errorText}`);
          
          await trackServiceEvent('apiKeyValidations', {
            service: 'alpaca',
            keyValid: false,
            errorMessage: errorText
          });
        }
        
        // Test with potentially valid key (if available)
        if (testConfig.testApiKeys.alpaca.key !== 'PKTest123') {
          await page.fill('[data-testid="alpaca-api-key"]', testConfig.testApiKeys.alpaca.key);
          await page.fill('[data-testid="alpaca-api-secret"]', testConfig.testApiKeys.alpaca.secret);
          
          await page.click('[data-testid="test-alpaca-connection"]');
          await page.waitForTimeout(8000);
          
          const alpacaSuccess = page.locator('[data-testid="alpaca-validation-success"]');
          if (await alpacaSuccess.isVisible()) {
            console.log('✅ Alpaca API key validation successful');
            
            await trackServiceEvent('apiKeyValidations', {
              service: 'alpaca',
              keyValid: true
            });
          }
        }
      }
      
      // 3. Test Polygon API key validation
      console.log('📈 Testing Polygon API key validation...');
      
      const polygonSection = page.locator('[data-testid="polygon-api-section"]');
      if (await polygonSection.isVisible()) {
        // Test with invalid key
        await page.fill('[data-testid="polygon-api-key"]', testConfig.testApiKeys.polygon.invalidKey);
        await page.click('[data-testid="test-polygon-connection"]');
        
        await page.waitForTimeout(8000);
        
        const polygonError = page.locator('[data-testid="polygon-validation-error"]');
        if (await polygonError.isVisible()) {
          const errorText = await polygonError.textContent();
          console.log(`🚨 Polygon invalid key error: ${errorText}`);
          
          await trackServiceEvent('apiKeyValidations', {
            service: 'polygon',
            keyValid: false,
            errorMessage: errorText
          });
        }
        
        // Test with potentially valid key
        if (testConfig.testApiKeys.polygon.key !== 'PolygonTest789') {
          await page.fill('[data-testid="polygon-api-key"]', testConfig.testApiKeys.polygon.key);
          await page.click('[data-testid="test-polygon-connection"]');
          
          await page.waitForTimeout(8000);
          
          const polygonSuccess = page.locator('[data-testid="polygon-validation-success"]');
          if (await polygonSuccess.isVisible()) {
            console.log('✅ Polygon API key validation successful');
            
            await trackServiceEvent('apiKeyValidations', {
              service: 'polygon',
              keyValid: true
            });
          }
        }
      }
      
      // 4. Test Finnhub API key validation
      console.log('📰 Testing Finnhub API key validation...');
      
      const finnhubSection = page.locator('[data-testid="finnhub-api-section"]');
      if (await finnhubSection.isVisible()) {
        await page.fill('[data-testid="finnhub-api-key"]', testConfig.testApiKeys.finnhub.invalidKey);
        await page.click('[data-testid="test-finnhub-connection"]');
        
        await page.waitForTimeout(6000);
        
        const finnhubError = page.locator('[data-testid="finnhub-validation-error"]');
        if (await finnhubError.isVisible()) {
          const errorText = await finnhubError.textContent();
          console.log(`🚨 Finnhub invalid key error: ${errorText}`);
          
          await trackServiceEvent('apiKeyValidations', {
            service: 'finnhub',
            keyValid: false,
            errorMessage: errorText
          });
        }
      }
      
      // 5. Test API key security features
      console.log('🔒 Testing API key security features...');
      
      const keyVisibilityToggle = page.locator('[data-testid="toggle-key-visibility"]');
      if (await keyVisibilityToggle.isVisible()) {
        await keyVisibilityToggle.click();
        
        // Check if keys are masked/unmasked appropriately
        const alpacaKeyField = page.locator('[data-testid="alpaca-api-key"]');
        const keyType = await alpacaKeyField.getAttribute('type');
        console.log(`🔒 API key field type after toggle: ${keyType}`);
      }
      
      // 6. Test API key encryption/storage
      const encryptionStatus = page.locator('[data-testid="encryption-status"]');
      if (await encryptionStatus.isVisible()) {
        const encryptionText = await encryptionStatus.textContent();
        console.log(`🔐 API key encryption status: ${encryptionText}`);
      }
      
      console.log('✅ Real API Key Validation and Management test completed');
    });

    test('API Key Rotation and Security Monitoring', async ({ page }) => {
      console.log('🔄 Testing API Key Rotation and Security Monitoring...');
      
      await authenticate(page);
      
      // 1. Navigate to advanced API key settings
      await page.goto('/settings/api-keys/advanced');
      await page.waitForSelector('[data-testid="advanced-api-settings"]', { timeout: 15000 });
      
      // 2. Test API key rotation warnings
      const rotationWarnings = page.locator('[data-testid^="rotation-warning-"]');
      const warningCount = await rotationWarnings.count();
      
      if (warningCount > 0) {
        console.log(`⚠️ API key rotation warnings: ${warningCount}`);
        
        for (let i = 0; i < warningCount; i++) {
          const warning = rotationWarnings.nth(i);
          const service = await warning.getAttribute('data-service');
          const warningText = await warning.textContent();
          
          console.log(`⚠️ ${service} rotation warning: ${warningText}`);
          
          await trackServiceEvent('apiKeyValidations', {
            service: service,
            type: 'rotation_warning',
            message: warningText
          });
        }
      }
      
      // 3. Test API usage monitoring
      const usageMonitoring = page.locator('[data-testid="api-usage-monitoring"]');
      if (await usageMonitoring.isVisible()) {
        console.log('📊 Testing API usage monitoring...');
        
        const services = ['alpaca', 'polygon', 'finnhub'];
        
        for (const service of services) {
          const usageStats = page.locator(`[data-testid="${service}-usage-stats"]`);
          if (await usageStats.isVisible()) {
            const usageData = {
              dailyRequests: await page.locator(`[data-testid="${service}-daily-requests"]`).textContent().catch(() => 'N/A'),
              monthlyRequests: await page.locator(`[data-testid="${service}-monthly-requests"]`).textContent().catch(() => 'N/A'),
              rateLimitStatus: await page.locator(`[data-testid="${service}-rate-limit-status"]`).textContent().catch(() => 'N/A')
            };
            
            console.log(`📊 ${service} usage:`, usageData);
            
            await trackServiceEvent('serviceConnections', {
              service: service,
              type: 'usage_stats',
              data: usageData
            });
          }
        }
      }
      
      // 4. Test suspicious activity detection
      const suspiciousActivity = page.locator('[data-testid="suspicious-activity-alerts"]');
      if (await suspiciousActivity.isVisible()) {
        const alerts = page.locator('[data-testid^="security-alert-"]');
        const alertCount = await alerts.count();
        
        if (alertCount > 0) {
          console.log(`🚨 Security alerts detected: ${alertCount}`);
          
          for (let i = 0; i < alertCount; i++) {
            const alert = alerts.nth(i);
            const alertType = await alert.getAttribute('data-alert-type');
            const alertMessage = await alert.textContent();
            
            console.log(`🚨 Security alert (${alertType}): ${alertMessage}`);
            
            await trackServiceEvent('serviceErrors', {
              type: 'security_alert',
              alertType: alertType,
              message: alertMessage
            });
          }
        }
      }
      
      console.log('✅ API Key Rotation and Security Monitoring test completed');
    });

  });

  test.describe('External Service Reliability and Fallbacks @critical @enterprise @service-reliability', () => {

    test('Market Data Service Reliability Testing', async ({ page, request }) => {
      console.log('📊 Testing Market Data Service Reliability...');
      
      await authenticate(page);
      
      // 1. Test primary market data source
      console.log('📈 Testing primary market data source reliability...');
      
      await page.goto('/market');
      await page.waitForSelector('[data-testid="market-page"]', { timeout: 15000 });
      
      // Monitor data loading from multiple sources
      const dataSourceIndicators = page.locator('[data-testid^="data-source-"]');
      const sourceCount = await dataSourceIndicators.count();
      
      console.log(`📊 Active data sources: ${sourceCount}`);
      
      for (let i = 0; i < sourceCount; i++) {
        const indicator = dataSourceIndicators.nth(i);
        const sourceName = await indicator.getAttribute('data-source-name');
        const sourceStatus = await indicator.textContent();
        
        console.log(`📊 ${sourceName}: ${sourceStatus}`);
        
        await trackServiceEvent('serviceConnections', {
          service: sourceName,
          status: sourceStatus,
          healthy: sourceStatus.includes('active') || sourceStatus.includes('connected')
        });
      }
      
      // 2. Test service failover mechanisms
      console.log('🔄 Testing service failover mechanisms...');
      
      const serviceFailover = page.locator('[data-testid="service-failover-status"]');
      if (await serviceFailover.isVisible()) {
        const failoverText = await serviceFailover.textContent();
        console.log(`🔄 Failover status: ${failoverText}`);
        
        if (failoverText.includes('fallback') || failoverText.includes('secondary')) {
          console.log('🔄 Fallback service detected');
          
          await trackServiceEvent('fallbackEvents', {
            type: 'service_fallback_active',
            details: failoverText
          });
        }
      }
      
      // 3. Test data quality from different sources
      console.log('📊 Testing data quality from different sources...');
      
      const testSymbols = ['AAPL', 'MSFT', 'GOOGL'];
      
      for (const symbol of testSymbols) {
        // Get quote from primary source
        const response = await request.get(`${testConfig.apiURL}/api/stocks/${symbol}/quote`);
        
        if (response.ok()) {
          const quoteData = await response.json();
          
          await trackServiceEvent('dataQuality', {
            symbol: symbol,
            source: quoteData.source || 'unknown',
            price: quoteData.price,
            volume: quoteData.volume,
            lastUpdate: quoteData.lastUpdate,
            dataComplete: !!(quoteData.price && quoteData.volume)
          });
          
          console.log(`📊 ${symbol} data quality: Price: ${quoteData.price}, Volume: ${quoteData.volume}, Source: ${quoteData.source}`);
        } else {
          console.log(`🚨 Failed to get ${symbol} data: ${response.status()}`);
          
          await trackServiceEvent('serviceErrors', {
            type: 'data_fetch_failure',
            symbol: symbol,
            status: response.status()
          });
        }
      }
      
      // 4. Test real-time data stream reliability
      console.log('📡 Testing real-time data stream reliability...');
      
      await page.goto('/market/live');
      await page.waitForSelector('[data-testid="live-market-data"]', { timeout: 15000 });
      
      // Monitor streaming status
      const streamingStatus = page.locator('[data-testid="streaming-status"]');
      if (await streamingStatus.isVisible()) {
        const statusText = await streamingStatus.textContent();
        console.log(`📡 Streaming status: ${statusText}`);
        
        await trackServiceEvent('serviceConnections', {
          service: 'real_time_data',
          status: statusText,
          type: 'streaming_status'
        });
      }
      
      // Monitor for data interruptions
      await page.waitForTimeout(15000);
      
      const dataInterruption = page.locator('[data-testid="data-interruption-notice"]');
      if (await dataInterruption.isVisible()) {
        const interruptionText = await dataInterruption.textContent();
        console.log(`⚠️ Data interruption detected: ${interruptionText}`);
        
        await trackServiceEvent('serviceErrors', {
          type: 'data_interruption',
          message: interruptionText
        });
      }
      
      console.log('✅ Market Data Service Reliability Testing completed');
    });

    test('Trading Service Integration and Reliability', async ({ page }) => {
      console.log('💼 Testing Trading Service Integration and Reliability...');
      
      await authenticate(page);
      
      // 1. Test Alpaca trading service connection
      console.log('📊 Testing Alpaca trading service connection...');
      
      await page.goto('/trading');
      await page.waitForSelector('[data-testid="trading-page"]', { timeout: 15000 });
      
      // Check trading service status
      const tradingServiceStatus = page.locator('[data-testid="trading-service-status"]');
      if (await tradingServiceStatus.isVisible()) {
        const statusText = await tradingServiceStatus.textContent();
        console.log(`💼 Trading service status: ${statusText}`);
        
        await trackServiceEvent('serviceConnections', {
          service: 'alpaca_trading',
          status: statusText,
          healthy: statusText.includes('connected') || statusText.includes('active')
        });
      }
      
      // 2. Test account connection
      const accountConnection = page.locator('[data-testid="account-connection-status"]');
      if (await accountConnection.isVisible()) {
        const accountText = await accountConnection.textContent();
        console.log(`👤 Account connection: ${accountText}`);
        
        if (accountText.includes('disconnected') || accountText.includes('error')) {
          await trackServiceEvent('serviceErrors', {
            type: 'account_connection_error',
            message: accountText
          });
        }
      }
      
      // 3. Test trading capabilities
      console.log('💰 Testing trading capabilities...');
      
      const tradingCapabilities = {
        'buy-orders': '[data-testid="buy-orders-available"]',
        'sell-orders': '[data-testid="sell-orders-available"]',
        'margin-trading': '[data-testid="margin-trading-available"]',
        'options-trading': '[data-testid="options-trading-available"]'
      };
      
      for (const [capability, selector] of Object.entries(tradingCapabilities)) {
        const element = page.locator(selector);
        if (await element.isVisible()) {
          const capabilityText = await element.textContent();
          console.log(`💼 ${capability}: ${capabilityText}`);
          
          await trackServiceEvent('serviceConnections', {
            service: 'alpaca_trading',
            capability: capability,
            available: capabilityText.includes('available') || capabilityText.includes('enabled')
          });
        }
      }
      
      // 4. Test order validation
      console.log('📋 Testing order validation...');
      
      await page.click('[data-testid="place-order-button"]');
      await page.waitForSelector('[data-testid="order-form"]', { timeout: 10000 });
      
      // Test validation with invalid order
      await page.fill('[data-testid="symbol-input"]', 'AAPL');
      await page.fill('[data-testid="quantity-input"]', '999999'); // Large quantity to trigger validation
      await page.fill('[data-testid="price-input"]', '0.01'); // Very low price
      
      await page.click('[data-testid="validate-order"]');
      await page.waitForTimeout(5000);
      
      const orderValidationError = page.locator('[data-testid="order-validation-error"]');
      if (await orderValidationError.isVisible()) {
        const validationText = await orderValidationError.textContent();
        console.log(`📋 Order validation error (expected): ${validationText}`);
        
        await trackServiceEvent('serviceConnections', {
          service: 'alpaca_trading',
          type: 'order_validation',
          validationWorking: true
        });
      }
      
      // 5. Test market hours integration
      const marketHoursStatus = page.locator('[data-testid="market-hours-status"]');
      if (await marketHoursStatus.isVisible()) {
        const hoursText = await marketHoursStatus.textContent();
        console.log(`🕐 Market hours status: ${hoursText}`);
        
        await trackServiceEvent('serviceConnections', {
          service: 'market_hours',
          status: hoursText
        });
      }
      
      console.log('✅ Trading Service Integration and Reliability completed');
    });

  });

  test.describe('Rate Limiting and Service Quotas @critical @enterprise @rate-limits', () => {

    test('API Rate Limiting Detection and Handling', async ({ page, request }) => {
      console.log('🚫 Testing API Rate Limiting Detection and Handling...');
      
      await authenticate(page);
      
      // 1. Test rate limiting with rapid requests
      console.log('⚡ Testing rate limiting with rapid requests...');
      
      const testEndpoints = [
        '/api/stocks/AAPL/quote',
        '/api/stocks/MSFT/quote',
        '/api/market/overview'
      ];
      
      for (const endpoint of testEndpoints) {
        console.log(`⚡ Testing rate limits on ${endpoint}...`);
        
        const responses = [];
        const requestCount = 25; // High number to potentially trigger rate limits
        
        // Make rapid concurrent requests
        const promises = [];
        for (let i = 0; i < requestCount; i++) {
          promises.push(
            request.get(`${testConfig.apiURL}${endpoint}`)
              .then(response => ({
                status: response.status(),
                headers: response.headers(),
                responseTime: Date.now()
              }))
              .catch(error => ({
                error: error.message,
                status: 0
              }))
          );
        }
        
        const results = await Promise.all(promises);
        
        // Analyze responses for rate limiting
        const rateLimitedResponses = results.filter(r => r.status === 429);
        const successfulResponses = results.filter(r => r.status === 200);
        
        console.log(`📊 ${endpoint}: ${successfulResponses.length} successful, ${rateLimitedResponses.length} rate limited`);
        
        if (rateLimitedResponses.length > 0) {
          console.log(`🚫 Rate limiting detected on ${endpoint}`);
          
          // Check rate limit headers
          const rateLimitInfo = rateLimitedResponses[0].headers;
          console.log(`Rate limit headers:`, {
            limit: rateLimitInfo['x-ratelimit-limit'],
            remaining: rateLimitInfo['x-ratelimit-remaining'],
            reset: rateLimitInfo['x-ratelimit-reset']
          });
          
          await trackServiceEvent('rateLimits', {
            endpoint: endpoint,
            totalRequests: requestCount,
            rateLimitedCount: rateLimitedResponses.length,
            rateLimitHeaders: rateLimitInfo
          });
        }
        
        // Wait between endpoint tests
        await page.waitForTimeout(5000);
      }
      
      // 2. Test rate limit recovery
      console.log('🔄 Testing rate limit recovery...');
      
      await page.goto('/admin/rate-limit-monitor');
      await page.waitForSelector('[data-testid="rate-limit-monitor"]', { timeout: 15000 });
      
      const rateLimitStatus = page.locator('[data-testid^="rate-limit-status-"]');
      const statusCount = await rateLimitStatus.count();
      
      for (let i = 0; i < statusCount; i++) {
        const status = rateLimitStatus.nth(i);
        const service = await status.getAttribute('data-service');
        const statusText = await status.textContent();
        
        console.log(`🚫 ${service} rate limit status: ${statusText}`);
        
        if (statusText.includes('limited') || statusText.includes('exceeded')) {
          await trackServiceEvent('rateLimits', {
            service: service,
            status: 'rate_limited',
            details: statusText
          });
        }
      }
      
      // 3. Test quota management
      const quotaManagement = page.locator('[data-testid="quota-management"]');
      if (await quotaManagement.isVisible()) {
        console.log('📊 Testing quota management...');
        
        const services = ['alpaca', 'polygon', 'finnhub'];
        
        for (const service of services) {
          const quotaInfo = page.locator(`[data-testid="${service}-quota-info"]`);
          if (await quotaInfo.isVisible()) {
            const quotaText = await quotaInfo.textContent();
            console.log(`📊 ${service} quota: ${quotaText}`);
            
            // Check for quota warnings
            const quotaWarning = page.locator(`[data-testid="${service}-quota-warning"]`);
            if (await quotaWarning.isVisible()) {
              const warningText = await quotaWarning.textContent();
              console.log(`⚠️ ${service} quota warning: ${warningText}`);
              
              await trackServiceEvent('rateLimits', {
                service: service,
                type: 'quota_warning',
                message: warningText
              });
            }
          }
        }
      }
      
      console.log('✅ API Rate Limiting Detection and Handling completed');
    });

  });

  test.describe('Service Health and Monitoring @critical @enterprise @service-health', () => {

    test('External Service Health Dashboard', async ({ page }) => {
      console.log('📊 Testing External Service Health Dashboard...');
      
      await authenticate(page);
      
      // 1. Navigate to service health dashboard
      await page.goto('/admin/service-health');
      await page.waitForSelector('[data-testid="service-health-dashboard"]', { timeout: 15000 });
      
      // 2. Check overall service status
      const overallStatus = page.locator('[data-testid="overall-service-status"]');
      if (await overallStatus.isVisible()) {
        const statusText = await overallStatus.textContent();
        console.log(`📊 Overall service status: ${statusText}`);
        
        await trackServiceEvent('serviceConnections', {
          type: 'overall_status',
          status: statusText
        });
      }
      
      // 3. Check individual service health
      const services = ['alpaca', 'polygon', 'finnhub', 'database', 'cache', 'websocket'];
      
      for (const service of services) {
        const serviceHealth = page.locator(`[data-testid="${service}-health-status"]`);
        if (await serviceHealth.isVisible()) {
          const healthText = await serviceHealth.textContent();
          console.log(`📊 ${service} health: ${healthText}`);
          
          await trackServiceEvent('serviceConnections', {
            service: service,
            health: healthText,
            healthy: healthText.includes('healthy') || healthText.includes('operational')
          });
          
          // Check for service alerts
          const serviceAlert = page.locator(`[data-testid="${service}-health-alert"]`);
          if (await serviceAlert.isVisible()) {
            const alertText = await serviceAlert.textContent();
            console.log(`🚨 ${service} alert: ${alertText}`);
            
            await trackServiceEvent('serviceErrors', {
              service: service,
              type: 'health_alert',
              message: alertText
            });
          }
        }
      }
      
      // 4. Test service health history
      const healthHistory = page.locator('[data-testid="service-health-history"]');
      if (await healthHistory.isVisible()) {
        console.log('📈 Checking service health history...');
        
        const historyEntries = page.locator('[data-testid^="health-history-"]');
        const entryCount = await historyEntries.count();
        
        console.log(`📈 Health history entries: ${entryCount}`);
        
        if (entryCount > 0) {
          // Check recent incidents
          const recentIncidents = page.locator('[data-testid^="incident-"]');
          const incidentCount = await recentIncidents.count();
          
          if (incidentCount > 0) {
            console.log(`🚨 Recent incidents: ${incidentCount}`);
            
            for (let i = 0; i < Math.min(3, incidentCount); i++) {
              const incident = recentIncidents.nth(i);
              const incidentText = await incident.textContent();
              console.log(`🚨 Incident ${i + 1}: ${incidentText}`);
              
              await trackServiceEvent('serviceErrors', {
                type: 'historical_incident',
                message: incidentText
              });
            }
          }
        }
      }
      
      // 5. Test automated health checks
      const runHealthCheck = page.locator('[data-testid="run-health-check"]');
      if (await runHealthCheck.isVisible()) {
        console.log('🔍 Running manual health check...');
        
        await runHealthCheck.click();
        await page.waitForTimeout(10000);
        
        const healthCheckResults = page.locator('[data-testid="health-check-results"]');
        if (await healthCheckResults.isVisible()) {
          const resultsText = await healthCheckResults.textContent();
          console.log(`🔍 Health check results: ${resultsText}`);
          
          await trackServiceEvent('serviceConnections', {
            type: 'manual_health_check',
            results: resultsText
          });
        }
      }
      
      console.log('✅ External Service Health Dashboard completed');
    });

  });

  test.afterEach(async () => {
    // External services session summary
    console.log('\n🌐 External Services Integration Session Summary:');
    console.log(`API key validations: ${servicesSession.apiKeyValidations.length}`);
    console.log(`Service connections: ${servicesSession.serviceConnections.length}`);
    console.log(`Data quality checks: ${servicesSession.dataQuality.length}`);
    console.log(`Rate limit events: ${servicesSession.rateLimits.length}`);
    console.log(`Service errors: ${servicesSession.serviceErrors.length}`);
    console.log(`Fallback events: ${servicesSession.fallbackEvents.length}`);
    console.log(`Total errors: ${servicesSession.errors.length}`);
    
    // Log API key validation results
    if (servicesSession.apiKeyValidations.length > 0) {
      console.log('\n🔑 API Key Validation Results:');
      const validationSummary = servicesSession.apiKeyValidations.reduce((acc, validation) => {
        const service = validation.service;
        if (!acc[service]) acc[service] = { valid: 0, invalid: 0 };
        validation.keyValid ? acc[service].valid++ : acc[service].invalid++;
        return acc;
      }, {});
      
      Object.entries(validationSummary).forEach(([service, counts]) => {
        console.log(`  ${service}: ${counts.valid} valid, ${counts.invalid} invalid`);
      });
    }
    
    // Log service health summary
    if (servicesSession.serviceConnections.length > 0) {
      console.log('\n📊 Service Health Summary:');
      const healthSummary = servicesSession.serviceConnections.reduce((acc, connection) => {
        const service = connection.service;
        if (!acc[service]) acc[service] = { healthy: 0, unhealthy: 0 };
        connection.healthy ? acc[service].healthy++ : acc[service].unhealthy++;
        return acc;
      }, {});
      
      Object.entries(healthSummary).forEach(([service, counts]) => {
        console.log(`  ${service}: ${counts.healthy} healthy, ${counts.unhealthy} unhealthy checks`);
      });
    }
    
    // Log rate limiting incidents
    if (servicesSession.rateLimits.length > 0) {
      console.log('\n🚫 Rate Limiting Summary:');
      servicesSession.rateLimits.forEach(rateLimit => {
        console.log(`  ${rateLimit.service || rateLimit.endpoint}: ${rateLimit.type || 'rate_limited'}`);
      });
    }
    
    // Log critical service errors
    const criticalErrors = servicesSession.serviceErrors.filter(error => 
      error.type.includes('security') || error.type.includes('health_alert') || error.type.includes('connection')
    );
    
    if (criticalErrors.length > 0) {
      console.log('\n🚨 Critical Service Errors:');
      criticalErrors.forEach(error => {
        console.log(`  ${error.timestamp}: ${error.type} - ${error.message}`);
      });
    }
    
    // Calculate service reliability score
    const totalConnections = servicesSession.serviceConnections.length;
    const healthyConnections = servicesSession.serviceConnections.filter(conn => conn.healthy).length;
    const reliabilityScore = totalConnections > 0 ? (healthyConnections / totalConnections * 100).toFixed(1) : 100;
    
    console.log(`\n📈 Overall Service Reliability Score: ${reliabilityScore}% (${healthyConnections}/${totalConnections})`);
  });

});

export default {
  testConfig
};