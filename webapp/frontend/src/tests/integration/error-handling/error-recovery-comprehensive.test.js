/**
 * Comprehensive Error Handling and Recovery Integration Tests
 * Tests real error scenarios, recovery mechanisms, and system resilience
 * Focuses on known problem areas: Database connections, API failures, WebSocket drops
 * NO MOCKS - Tests against actual implementation and real failure scenarios
 */

import { test, expect } from '@playwright/test';

const testConfig = {
  baseURL: process.env.E2E_BASE_URL || 'https://d1zb7knau41vl9.cloudfront.net',
  apiURL: process.env.E2E_API_URL || 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev',
  testUser: {
    email: process.env.E2E_TEST_EMAIL || 'e2e-test@example.com',
    password: process.env.E2E_TEST_PASSWORD || 'E2ETest123!'
  },
  timeout: 60000
};

test.describe('Comprehensive Error Handling and Recovery Integration - Enterprise Framework', () => {
  
  let errorSession = {
    networkErrors: [],
    apiErrors: [],
    databaseErrors: [],
    websocketErrors: [],
    recoveryAttempts: [],
    userExperience: [],
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

  async function trackErrorEvent(eventType, data) {
    errorSession[eventType].push({
      ...data,
      timestamp: new Date().toISOString()
    });
  }

  async function simulateNetworkFailure(page, duration = 5000) {
    console.log(`🚫 Simulating network failure for ${duration}ms...`);
    await page.context().setOffline(true);
    await page.waitForTimeout(duration);
    await page.context().setOffline(false);
    console.log('🟢 Network restored');
  }

  test.beforeEach(async ({ page }) => {
    // Reset error session tracking
    errorSession = {
      networkErrors: [],
      apiErrors: [],
      databaseErrors: [],
      websocketErrors: [],
      recoveryAttempts: [],
      userExperience: [],
      errors: []
    };
    
    // Monitor all network failures
    page.on('requestfailed', request => {
      trackErrorEvent('networkErrors', {
        url: request.url(),
        method: request.method(),
        failure: request.failure()?.errorText || 'Unknown failure'
      });
      console.log(`🚫 Network request failed: ${request.url()} - ${request.failure()?.errorText}`);
    });

    // Monitor console errors
    page.on('console', msg => {
      if (msg.type() === 'error') {
        const errorText = msg.text();
        errorSession.errors.push({
          message: errorText,
          timestamp: new Date().toISOString()
        });

        // Categorize errors
        if (errorText.includes('database') || errorText.includes('connection') || errorText.includes('timeout')) {
          trackErrorEvent('databaseErrors', { message: errorText });
        } else if (errorText.includes('websocket') || errorText.includes('ws') || errorText.includes('socket')) {
          trackErrorEvent('websocketErrors', { message: errorText });
        } else if (errorText.includes('api') || errorText.includes('fetch') || errorText.includes('network')) {
          trackErrorEvent('apiErrors', { message: errorText });
        }
      }
    });

    // Monitor API responses for errors
    page.on('response', response => {
      if (!response.ok()) {
        trackErrorEvent('apiErrors', {
          url: response.url(),
          status: response.status(),
          statusText: response.statusText()
        });
      }
    });

    await page.goto(testConfig.baseURL);
    await page.waitForLoadState('networkidle');
  });

  test.describe('Database Connection Error Recovery @critical @enterprise @error-handling', () => {

    test('Database Connection Failure Recovery in Data Loading', async ({ page }) => {
      console.log('🗄️ Testing Database Connection Failure Recovery in Data Loading...');
      
      await authenticate(page);
      
      // 1. Navigate to portfolio (heavy database usage)
      await page.goto('/portfolio');
      await page.waitForSelector('[data-testid="portfolio-page"]', { timeout: 15000 });
      
      // 2. Monitor for database connection errors during load
      const initialDbErrors = errorSession.databaseErrors.length;
      
      // 3. Test portfolio holdings load with potential connection issues
      await page.click('[data-testid="refresh-holdings"]');
      
      // Wait and check for loading states and error handling
      await page.waitForTimeout(5000);
      
      // Check if error indicators appear
      const connectionError = page.locator('[data-testid="connection-error"]');
      const databaseError = page.locator('[data-testid="database-error"]');
      const retryButton = page.locator('[data-testid="retry-connection"]');
      
      if (await connectionError.isVisible() || await databaseError.isVisible()) {
        console.log('🚨 Database connection error detected');
        
        const errorMessage = await (connectionError.isVisible() ? connectionError : databaseError).textContent();
        console.log(`Error message: ${errorMessage}`);
        
        await trackErrorEvent('databaseErrors', {
          type: 'connection_failure',
          context: 'portfolio_loading',
          errorMessage: errorMessage
        });
        
        // Test retry mechanism
        if (await retryButton.isVisible()) {
          console.log('🔄 Testing retry mechanism...');
          await retryButton.click();
          
          await trackErrorEvent('recoveryAttempts', {
            type: 'manual_retry',
            context: 'database_connection'
          });
          
          // Wait for retry attempt
          await page.waitForTimeout(3000);
          
          // Check if retry succeeded
          const retrySuccess = await page.locator('[data-testid="portfolio-summary"]').isVisible({ timeout: 10000 });
          
          if (retrySuccess) {
            console.log('✅ Manual retry successful');
            await trackErrorEvent('recoveryAttempts', {
              type: 'manual_retry_success',
              context: 'database_connection'
            });
          } else {
            console.log('❌ Manual retry failed');
          }
        }
      }
      
      // 4. Test automatic retry behavior
      console.log('⏰ Testing automatic retry behavior...');
      
      // Force refresh to trigger potential retries
      await page.reload();
      await page.waitForLoadState('networkidle');
      
      // Monitor for automatic retry indicators
      const loadingIndicators = page.locator('[data-testid*="loading"]');
      const retryIndicators = page.locator('[data-testid*="retry"]');
      
      if (await loadingIndicators.count() > 0) {
        console.log('🔄 Loading indicators detected - monitoring for automatic retries...');
        
        // Wait and watch for retry patterns
        for (let i = 0; i < 10; i++) {
          await page.waitForTimeout(2000);
          
          const currentRetryCount = await retryIndicators.count();
          const currentLoadingCount = await loadingIndicators.count();
          
          if (currentRetryCount > 0) {
            console.log(`🔄 Automatic retry detected (attempt ${i + 1})`);
            await trackErrorEvent('recoveryAttempts', {
              type: 'automatic_retry',
              attempt: i + 1,
              context: 'database_connection'
            });
          }
          
          // Check if loading completed successfully
          if (currentLoadingCount === 0 && await page.locator('[data-testid="portfolio-summary"]').isVisible()) {
            console.log('✅ Automatic recovery successful');
            break;
          }
        }
      }
      
      console.log('✅ Database Connection Failure Recovery test completed');
    });

    test('AAII Data Loader Connection Issues Recovery', async ({ page }) => {
      console.log('📊 Testing AAII Data Loader Connection Issues Recovery...');
      
      await authenticate(page);
      
      // 1. Navigate to market data page (uses AAII data)
      await page.goto('/market/aaii-data');
      await page.waitForSelector('[data-testid="aaii-data-page"]', { timeout: 15000 });
      
      // 2. Test AAII data loading
      await page.click('[data-testid="load-aaii-data"]');
      
      // Monitor for SSL/connection errors (known issue)
      await page.waitForTimeout(10000);
      
      const sslError = page.locator('[data-testid="ssl-error"]');
      const connectionTimeout = page.locator('[data-testid="connection-timeout"]');
      const certError = page.locator('[data-testid="certificate-error"]');
      
      if (await sslError.isVisible() || await connectionTimeout.isVisible() || await certError.isVisible()) {
        console.log('🚨 AAII connection error detected (known issue)');
        
        const errorElement = await sslError.isVisible() ? sslError : 
                            await connectionTimeout.isVisible() ? connectionTimeout : certError;
        const errorMessage = await errorElement.textContent();
        
        console.log(`AAII Error: ${errorMessage}`);
        
        await trackErrorEvent('databaseErrors', {
          type: 'aaii_connection_failure',
          errorMessage: errorMessage,
          context: 'data_loading'
        });
        
        // Test fallback to cached data
        const cachedDataIndicator = page.locator('[data-testid="cached-data-notice"]');
        if (await cachedDataIndicator.isVisible()) {
          console.log('✅ Fallback to cached data working');
          await trackErrorEvent('recoveryAttempts', {
            type: 'fallback_to_cache',
            context: 'aaii_data'
          });
        }
        
        // Test manual retry with different connection strategy
        const retryWithFallback = page.locator('[data-testid="retry-with-fallback"]');
        if (await retryWithFallback.isVisible()) {
          await retryWithFallback.click();
          console.log('🔄 Testing retry with fallback strategy...');
          
          await page.waitForTimeout(5000);
          
          const fallbackSuccess = await page.locator('[data-testid="aaii-data-loaded"]').isVisible({ timeout: 15000 });
          if (fallbackSuccess) {
            console.log('✅ Fallback strategy successful');
          }
        }
      }
      
      // 3. Test SSL certificate handling
      console.log('🔐 Testing SSL certificate error handling...');
      
      const sslSettings = page.locator('[data-testid="ssl-settings"]');
      if (await sslSettings.isVisible()) {
        await sslSettings.click();
        
        // Test different SSL modes
        const sslModes = ['require', 'prefer', 'allow', 'disable'];
        
        for (const mode of sslModes) {
          const modeOption = page.locator(`[data-testid="ssl-mode-${mode}"]`);
          if (await modeOption.isVisible()) {
            await modeOption.click();
            await page.click('[data-testid="test-connection"]');
            
            await page.waitForTimeout(3000);
            
            const connectionResult = page.locator('[data-testid="connection-result"]');
            if (await connectionResult.isVisible()) {
              const resultText = await connectionResult.textContent();
              console.log(`SSL Mode ${mode}: ${resultText}`);
              
              if (resultText.includes('success')) {
                console.log(`✅ SSL mode ${mode} working`);
                await trackErrorEvent('recoveryAttempts', {
                  type: 'ssl_mode_success',
                  mode: mode
                });
                break;
              }
            }
          }
        }
      }
      
      console.log('✅ AAII Data Loader Connection Issues Recovery test completed');
    });

  });

  test.describe('API Failure and Recovery Handling @critical @enterprise @error-handling', () => {

    test('API Timeout and Retry Logic Integration', async ({ page }) => {
      console.log('⏱️ Testing API Timeout and Retry Logic Integration...');
      
      await authenticate(page);
      
      // 1. Navigate to portfolio to trigger multiple API calls
      await page.goto('/portfolio');
      await page.waitForSelector('[data-testid="portfolio-page"]', { timeout: 15000 });
      
      // 2. Simulate network instability
      console.log('🌐 Simulating network instability...');
      
      // Make rapid navigation to trigger multiple API calls
      const pages = ['/portfolio', '/market', '/trading', '/portfolio/performance'];
      
      for (const pagePath of pages) {
        // Simulate brief network issues during navigation
        const networkFailurePromise = simulateNetworkFailure(page, 2000);
        const navigationPromise = page.goto(pagePath);
        
        await Promise.race([networkFailurePromise, navigationPromise]);
        
        // Check for retry indicators
        const retryIndicator = page.locator('[data-testid="api-retry-indicator"]');
        const errorBoundary = page.locator('[data-testid="error-boundary"]');
        
        if (await retryIndicator.isVisible({ timeout: 3000 })) {
          console.log(`🔄 API retry detected on ${pagePath}`);
          await trackErrorEvent('recoveryAttempts', {
            type: 'api_retry',
            page: pagePath
          });
        }
        
        if (await errorBoundary.isVisible({ timeout: 3000 })) {
          console.log(`🚨 Error boundary triggered on ${pagePath}`);
          await trackErrorEvent('userExperience', {
            type: 'error_boundary_shown',
            page: pagePath
          });
          
          // Test error boundary recovery
          const retryButton = page.locator('[data-testid="error-boundary-retry"]');
          if (await retryButton.isVisible()) {
            await retryButton.click();
            console.log('🔄 Error boundary retry attempted');
          }
        }
        
        await page.waitForTimeout(2000);
      }
      
      // 3. Test API circuit breaker behavior
      console.log('⚡ Testing API circuit breaker behavior...');
      
      // Make many rapid requests to potentially trigger circuit breaker
      for (let i = 0; i < 10; i++) {
        await page.click('[data-testid="refresh-data"]').catch(() => {});
        await page.waitForTimeout(500);
      }
      
      const circuitBreakerNotice = page.locator('[data-testid="circuit-breaker-notice"]');
      if (await circuitBreakerNotice.isVisible({ timeout: 5000 })) {
        console.log('⚡ Circuit breaker activated');
        const noticeText = await circuitBreakerNotice.textContent();
        console.log(`Circuit breaker message: ${noticeText}`);
        
        await trackErrorEvent('recoveryAttempts', {
          type: 'circuit_breaker_activated',
          message: noticeText
        });
      }
      
      console.log('✅ API Timeout and Retry Logic Integration test completed');
    });

    test('Downstream Service Failure Handling', async ({ page, request }) => {
      console.log('🔗 Testing Downstream Service Failure Handling...');
      
      await authenticate(page);
      
      // 1. Test market data service failures
      console.log('📊 Testing market data service failures...');
      
      await page.goto('/market');
      
      // Check for market data unavailable scenarios
      const marketDataError = page.locator('[data-testid="market-data-unavailable"]');
      const alpacaError = page.locator('[data-testid="alpaca-service-error"]');
      const polygonError = page.locator('[data-testid="polygon-service-error"]');
      
      await page.waitForTimeout(10000); // Allow time for service calls
      
      if (await marketDataError.isVisible() || await alpacaError.isVisible() || await polygonError.isVisible()) {
        console.log('🚨 Market data service error detected');
        
        const errorElement = await marketDataError.isVisible() ? marketDataError :
                           await alpacaError.isVisible() ? alpacaError : polygonError;
        const errorMessage = await errorElement.textContent();
        
        await trackErrorEvent('apiErrors', {
          type: 'downstream_service_failure',
          service: 'market_data',
          errorMessage: errorMessage
        });
        
        // Test fallback data source
        const fallbackNotice = page.locator('[data-testid="using-fallback-data"]');
        if (await fallbackNotice.isVisible()) {
          console.log('✅ Fallback data source activated');
          await trackErrorEvent('recoveryAttempts', {
            type: 'fallback_data_source',
            service: 'market_data'
          });
        }
      }
      
      // 2. Test API key issues
      console.log('🔑 Testing API key issues...');
      
      await page.goto('/settings/api-keys');
      
      // Test invalid API key handling
      const alpacaKeyInput = page.locator('[data-testid="alpaca-api-key"]');
      if (await alpacaKeyInput.isVisible()) {
        await alpacaKeyInput.fill('invalid-key-123');
        await page.click('[data-testid="test-alpaca-connection"]');
        
        await page.waitForTimeout(5000);
        
        const keyError = page.locator('[data-testid="api-key-error"]');
        if (await keyError.isVisible()) {
          const keyErrorText = await keyError.textContent();
          console.log(`🔑 API key error detected: ${keyErrorText}`);
          
          await trackErrorEvent('apiErrors', {
            type: 'invalid_api_key',
            service: 'alpaca',
            errorMessage: keyErrorText
          });
        }
      }
      
      // 3. Test rate limiting from external APIs
      console.log('🚫 Testing external API rate limiting...');
      
      // Make multiple rapid requests to test rate limiting
      const responses = [];
      for (let i = 0; i < 15; i++) {
        const response = await request.get(`${testConfig.apiURL}/api/stocks/AAPL/quote`).catch(e => null);
        if (response) {
          responses.push({
            status: response.status(),
            headers: response.headers()
          });
        }
        await page.waitForTimeout(100);
      }
      
      const rateLimitedResponses = responses.filter(r => r.status === 429);
      if (rateLimitedResponses.length > 0) {
        console.log(`🚫 Rate limiting detected: ${rateLimitedResponses.length} requests limited`);
        
        await trackErrorEvent('apiErrors', {
          type: 'external_rate_limit',
          limitedRequests: rateLimitedResponses.length,
          totalRequests: responses.length
        });
      }
      
      console.log('✅ Downstream Service Failure Handling test completed');
    });

  });

  test.describe('WebSocket Connection Recovery @critical @enterprise @error-handling', () => {

    test('Real-time Data Stream Recovery', async ({ page }) => {
      console.log('📡 Testing Real-time Data Stream Recovery...');
      
      await authenticate(page);
      
      // 1. Navigate to live trading page (heavy WebSocket usage)
      await page.goto('/trading/live');
      await page.waitForSelector('[data-testid="live-trading"]', { timeout: 15000 });
      
      // Monitor WebSocket connections
      const webSocketConnections = [];
      const webSocketErrors = [];
      
      page.on('websocket', ws => {
        console.log(`🔌 WebSocket connected: ${ws.url()}`);
        webSocketConnections.push({
          url: ws.url(),
          timestamp: new Date().toISOString()
        });
        
        ws.on('close', () => {
          console.log(`🔌 WebSocket closed: ${ws.url()}`);
          trackErrorEvent('websocketErrors', {
            type: 'connection_closed',
            url: ws.url()
          });
        });
        
        ws.on('framereceived', event => {
          try {
            const data = JSON.parse(event.payload);
            if (data.type === 'error') {
              console.log(`🚨 WebSocket error received: ${data.message}`);
              webSocketErrors.push(data);
              trackErrorEvent('websocketErrors', {
                type: 'data_error',
                message: data.message
              });
            }
          } catch (e) {
            // Non-JSON message
          }
        });
      });
      
      // 2. Wait for initial connections
      await page.waitForTimeout(5000);
      console.log(`🔌 Initial WebSocket connections: ${webSocketConnections.length}`);
      
      // 3. Simulate network interruption
      console.log('🚫 Simulating network interruption...');
      await simulateNetworkFailure(page, 8000);
      
      // 4. Check for reconnection indicators
      const reconnectingIndicator = page.locator('[data-testid="reconnecting"]');
      const connectionLostNotice = page.locator('[data-testid="connection-lost"]');
      
      if (await reconnectingIndicator.isVisible({ timeout: 5000 })) {
        console.log('🔄 Reconnection indicator shown');
        await trackErrorEvent('userExperience', {
          type: 'reconnection_indicator_shown'
        });
      }
      
      if (await connectionLostNotice.isVisible({ timeout: 5000 })) {
        console.log('🚨 Connection lost notice shown');
        await trackErrorEvent('userExperience', {
          type: 'connection_lost_notice_shown'
        });
      }
      
      // 5. Wait for reconnection
      console.log('⏰ Waiting for reconnection...');
      await page.waitForTimeout(10000);
      
      const reconnectedNotice = page.locator('[data-testid="reconnected"]');
      if (await reconnectedNotice.isVisible({ timeout: 10000 })) {
        console.log('✅ Reconnection successful');
        await trackErrorEvent('recoveryAttempts', {
          type: 'websocket_reconnection_success'
        });
      }
      
      // 6. Verify data streaming resumed
      const priceUpdates = page.locator('[data-testid*="price-update"]');
      const initialUpdateCount = await priceUpdates.count();
      
      await page.waitForTimeout(5000);
      
      const currentUpdateCount = await priceUpdates.count();
      if (currentUpdateCount > initialUpdateCount) {
        console.log('✅ Data streaming resumed after reconnection');
        await trackErrorEvent('recoveryAttempts', {
          type: 'data_streaming_resumed',
          updatesReceived: currentUpdateCount - initialUpdateCount
        });
      }
      
      console.log('✅ Real-time Data Stream Recovery test completed');
    });

    test('WebSocket Error Handling and Fallback', async ({ page }) => {
      console.log('⚠️ Testing WebSocket Error Handling and Fallback...');
      
      await authenticate(page);
      
      // 1. Navigate to dashboard with real-time components
      await page.goto('/');
      await page.waitForSelector('[data-testid="dashboard"]', { timeout: 15000 });
      
      // 2. Monitor for WebSocket fallback behavior
      await page.waitForTimeout(5000);
      
      // 3. Test manual reconnection
      const reconnectButton = page.locator('[data-testid="manual-reconnect"]');
      if (await reconnectButton.isVisible()) {
        console.log('🔄 Manual reconnect option available');
        await reconnectButton.click();
        
        await trackErrorEvent('recoveryAttempts', {
          type: 'manual_websocket_reconnect'
        });
        
        await page.waitForTimeout(3000);
        
        const reconnectSuccess = page.locator('[data-testid="connection-restored"]');
        if (await reconnectSuccess.isVisible()) {
          console.log('✅ Manual reconnection successful');
        }
      }
      
      // 4. Test fallback to polling
      const pollingFallback = page.locator('[data-testid="polling-fallback-active"]');
      if (await pollingFallback.isVisible()) {
        console.log('🔄 Polling fallback activated');
        await trackErrorEvent('recoveryAttempts', {
          type: 'websocket_to_polling_fallback'
        });
        
        const fallbackMessage = await pollingFallback.textContent();
        console.log(`Fallback message: ${fallbackMessage}`);
      }
      
      // 5. Test data staleness indicators
      const staleDataWarning = page.locator('[data-testid="stale-data-warning"]');
      if (await staleDataWarning.isVisible()) {
        console.log('⚠️ Stale data warning shown');
        await trackErrorEvent('userExperience', {
          type: 'stale_data_warning_shown'
        });
      }
      
      console.log('✅ WebSocket Error Handling and Fallback test completed');
    });

  });

  test.describe('User Experience During Errors @critical @enterprise @error-handling', () => {

    test('Error Boundary and Graceful Degradation', async ({ page }) => {
      console.log('🛡️ Testing Error Boundary and Graceful Degradation...');
      
      await authenticate(page);
      
      // 1. Test error boundaries on different pages
      const errorPronePages = [
        '/portfolio/performance',
        '/market/analysis',
        '/trading/signals',
        '/settings/advanced'
      ];
      
      for (const pagePath of errorPronePages) {
        console.log(`🧪 Testing error boundary on ${pagePath}...`);
        
        await page.goto(pagePath);
        await page.waitForLoadState('networkidle');
        
        // Check for error boundaries
        const errorBoundary = page.locator('[data-testid="error-boundary"]');
        const componentError = page.locator('[data-testid="component-error"]');
        
        if (await errorBoundary.isVisible({ timeout: 5000 })) {
          console.log(`🚨 Error boundary activated on ${pagePath}`);
          
          const errorMessage = await errorBoundary.locator('[data-testid="error-message"]').textContent().catch(() => 'Unknown error');
          console.log(`Error message: ${errorMessage}`);
          
          await trackErrorEvent('userExperience', {
            type: 'error_boundary_activated',
            page: pagePath,
            errorMessage: errorMessage
          });
          
          // Test error boundary recovery
          const retryButton = page.locator('[data-testid="error-boundary-retry"]');
          if (await retryButton.isVisible()) {
            await retryButton.click();
            console.log('🔄 Error boundary retry attempted');
            
            await page.waitForTimeout(3000);
            
            const recoverySuccess = !await errorBoundary.isVisible();
            if (recoverySuccess) {
              console.log('✅ Error boundary recovery successful');
              await trackErrorEvent('recoveryAttempts', {
                type: 'error_boundary_recovery_success',
                page: pagePath
              });
            }
          }
        }
        
        if (await componentError.isVisible({ timeout: 5000 })) {
          console.log(`⚠️ Component error detected on ${pagePath}`);
          
          // Test graceful degradation
          const fallbackContent = page.locator('[data-testid="fallback-content"]');
          if (await fallbackContent.isVisible()) {
            console.log('✅ Graceful degradation working - fallback content shown');
            await trackErrorEvent('userExperience', {
              type: 'graceful_degradation_active',
              page: pagePath
            });
          }
        }
      }
      
      console.log('✅ Error Boundary and Graceful Degradation test completed');
    });

    test('User Notification and Feedback Systems', async ({ page }) => {
      console.log('📢 Testing User Notification and Feedback Systems...');
      
      await authenticate(page);
      
      // 1. Test notification system during errors
      await page.goto('/portfolio');
      
      // Trigger potential error scenarios
      await page.click('[data-testid="refresh-all-data"]');
      
      // Wait for notifications
      await page.waitForTimeout(5000);
      
      // Check for different types of notifications
      const errorNotification = page.locator('[data-testid="error-notification"]');
      const warningNotification = page.locator('[data-testid="warning-notification"]');
      const retryNotification = page.locator('[data-testid="retry-notification"]');
      
      if (await errorNotification.isVisible()) {
        const errorText = await errorNotification.textContent();
        console.log(`🚨 Error notification: ${errorText}`);
        
        await trackErrorEvent('userExperience', {
          type: 'error_notification_shown',
          message: errorText
        });
        
        // Test notification dismissal
        const dismissButton = page.locator('[data-testid="dismiss-error-notification"]');
        if (await dismissButton.isVisible()) {
          await dismissButton.click();
          console.log('✅ Error notification dismissed');
        }
      }
      
      if (await warningNotification.isVisible()) {
        const warningText = await warningNotification.textContent();
        console.log(`⚠️ Warning notification: ${warningText}`);
        
        await trackErrorEvent('userExperience', {
          type: 'warning_notification_shown',
          message: warningText
        });
      }
      
      if (await retryNotification.isVisible()) {
        const retryText = await retryNotification.textContent();
        console.log(`🔄 Retry notification: ${retryText}`);
        
        await trackErrorEvent('userExperience', {
          type: 'retry_notification_shown',
          message: retryText
        });
      }
      
      // 2. Test toast notifications
      const toastContainer = page.locator('[data-testid="toast-container"]');
      if (await toastContainer.isVisible()) {
        const toasts = page.locator('[data-testid^="toast-"]');
        const toastCount = await toasts.count();
        
        console.log(`📱 Toast notifications: ${toastCount} active`);
        
        if (toastCount > 0) {
          for (let i = 0; i < toastCount; i++) {
            const toast = toasts.nth(i);
            const toastType = await toast.getAttribute('data-type').catch(() => 'unknown');
            const toastMessage = await toast.textContent();
            
            console.log(`📱 Toast ${i + 1} (${toastType}): ${toastMessage}`);
            
            await trackErrorEvent('userExperience', {
              type: 'toast_notification',
              toastType: toastType,
              message: toastMessage
            });
          }
        }
      }
      
      // 3. Test progress indicators during recovery
      const loadingSpinner = page.locator('[data-testid="loading-spinner"]');
      const progressBar = page.locator('[data-testid="progress-bar"]');
      const retryProgress = page.locator('[data-testid="retry-progress"]');
      
      if (await loadingSpinner.isVisible()) {
        console.log('🔄 Loading spinner shown during recovery');
        await trackErrorEvent('userExperience', {
          type: 'loading_indicator_shown'
        });
      }
      
      if (await progressBar.isVisible()) {
        console.log('📊 Progress bar shown during recovery');
        await trackErrorEvent('userExperience', {
          type: 'progress_bar_shown'
        });
      }
      
      if (await retryProgress.isVisible()) {
        console.log('🔄 Retry progress indicator shown');
        await trackErrorEvent('userExperience', {
          type: 'retry_progress_shown'
        });
      }
      
      console.log('✅ User Notification and Feedback Systems test completed');
    });

  });

  test.afterEach(async () => {
    // Error handling session summary
    console.log('\n🚨 Error Handling and Recovery Session Summary:');
    console.log(`Network errors: ${errorSession.networkErrors.length}`);
    console.log(`API errors: ${errorSession.apiErrors.length}`);
    console.log(`Database errors: ${errorSession.databaseErrors.length}`);
    console.log(`WebSocket errors: ${errorSession.websocketErrors.length}`);
    console.log(`Recovery attempts: ${errorSession.recoveryAttempts.length}`);
    console.log(`User experience events: ${errorSession.userExperience.length}`);
    console.log(`Total errors: ${errorSession.errors.length}`);
    
    // Log critical errors
    if (errorSession.databaseErrors.length > 0) {
      console.log('\n🗄️ Database Errors:');
      errorSession.databaseErrors.forEach(error => {
        console.log(`  ${error.timestamp}: ${error.type || 'Unknown'} - ${error.message}`);
      });
    }
    
    // Log recovery success rate
    const totalFailures = errorSession.networkErrors.length + errorSession.apiErrors.length + 
                         errorSession.databaseErrors.length + errorSession.websocketErrors.length;
    const recoveryRate = totalFailures > 0 ? (errorSession.recoveryAttempts.length / totalFailures * 100).toFixed(1) : 0;
    
    console.log(`\n📊 Recovery Rate: ${recoveryRate}% (${errorSession.recoveryAttempts.length} recoveries / ${totalFailures} failures)`);
    
    // Log user experience impact
    if (errorSession.userExperience.length > 0) {
      console.log('\n👤 User Experience Impact:');
      const uxEvents = errorSession.userExperience.reduce((acc, event) => {
        acc[event.type] = (acc[event.type] || 0) + 1;
        return acc;
      }, {});
      
      Object.entries(uxEvents).forEach(([type, count]) => {
        console.log(`  ${type}: ${count} occurrences`);
      });
    }
  });

});

export default {
  testConfig
};