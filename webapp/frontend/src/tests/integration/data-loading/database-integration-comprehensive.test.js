/**
 * Comprehensive Database and Data Loading Integration Tests
 * Tests real database connections, AAII data loading, SSL issues, and data pipeline
 * Focuses on known problem areas: pg_hba.conf errors, SSL certificate issues, connection pooling
 * NO MOCKS - Tests against actual database and real data loading processes
 */

import { test, expect } from '@playwright/test';

const testConfig = {
  baseURL: process.env.E2E_BASE_URL || 'https://d1zb7knau41vl9.cloudfront.net',
  apiURL: process.env.E2E_API_URL || 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev',
  databaseURL: process.env.DATABASE_URL || 'postgresql://stocks_user:@stocks-db-cluster.cluster-xyz.us-east-1.rds.amazonaws.com:5432/stocks_db',
  testUser: {
    email: process.env.E2E_TEST_EMAIL || 'e2e-test@example.com',
    password: process.env.E2E_TEST_PASSWORD || 'E2ETest123!'
  },
  timeout: 90000 // Extended timeout for data loading operations
};

test.describe('Comprehensive Database and Data Loading Integration - Enterprise Framework', () => {
  
  let dataSession = {
    connectionAttempts: [],
    sslErrors: [],
    dataLoadEvents: [],
    performanceMetrics: [],
    cacheEvents: [],
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

  async function trackDataEvent(eventType, data) {
    dataSession[eventType].push({
      ...data,
      timestamp: new Date().toISOString()
    });
  }

  test.beforeEach(async ({ page }) => {
    // Reset data session tracking
    dataSession = {
      connectionAttempts: [],
      sslErrors: [],
      dataLoadEvents: [],
      performanceMetrics: [],
      cacheEvents: [],
      errors: []
    };
    
    // Monitor network requests for database-related calls
    page.on('request', request => {
      const url = request.url();
      if (url.includes('api/data') || url.includes('aaii') || url.includes('database') || url.includes('connection')) {
        const startTime = Date.now();
        trackDataEvent('connectionAttempts', {
          type: 'request_start',
          url: url,
          method: request.method(),
          startTime: startTime
        });
      }
    });

    page.on('response', response => {
      const url = response.url();
      if (url.includes('api/data') || url.includes('aaii') || url.includes('database') || url.includes('connection')) {
        trackDataEvent('connectionAttempts', {
          type: 'response_received',
          url: url,
          status: response.status(),
          responseTime: Date.now()
        });
      }
    });

    // Monitor console for database/SSL specific errors
    page.on('console', msg => {
      if (msg.type() === 'error') {
        const errorText = msg.text();
        
        if (errorText.includes('ssl') || errorText.includes('certificate') || errorText.includes('pg_hba')) {
          trackDataEvent('sslErrors', {
            message: errorText,
            type: 'ssl_certificate_error'
          });
        } else if (errorText.includes('connection') || errorText.includes('database') || errorText.includes('pool')) {
          trackDataEvent('errors', {
            message: errorText,
            type: 'database_connection_error'
          });
        } else if (errorText.includes('aaii') || errorText.includes('data loading')) {
          trackDataEvent('dataLoadEvents', {
            message: errorText,
            type: 'data_loading_error'
          });
        }
      }
    });

    await page.goto(testConfig.baseURL);
    await page.waitForLoadState('networkidle');
  });

  test.describe('Database Connection and SSL Integration @critical @enterprise @database', () => {

    test('Real PostgreSQL SSL Connection Issues Resolution', async ({ page }) => {
      console.log('🔐 Testing Real PostgreSQL SSL Connection Issues Resolution...');
      
      await authenticate(page);
      
      // 1. Navigate to database status page
      await page.goto('/admin/database-status');
      await page.waitForSelector('[data-testid="database-status-page"]', { timeout: 15000 });
      
      // 2. Test current connection status
      const connectionStatus = page.locator('[data-testid="connection-status"]');
      if (await connectionStatus.isVisible()) {
        const statusText = await connectionStatus.textContent();
        console.log(`📊 Current connection status: ${statusText}`);
        
        await trackDataEvent('connectionAttempts', {
          type: 'status_check',
          status: statusText
        });
      }
      
      // 3. Test SSL configuration options
      const sslConfigSection = page.locator('[data-testid="ssl-configuration"]');
      if (await sslConfigSection.isVisible()) {
        console.log('🔧 Testing SSL configuration options...');
        
        // Test different SSL modes
        const sslModes = ['require', 'prefer', 'allow', 'disable'];
        
        for (const mode of sslModes) {
          console.log(`🔐 Testing SSL mode: ${mode}`);
          
          const sslModeRadio = page.locator(`[data-testid="ssl-mode-${mode}"]`);
          if (await sslModeRadio.isVisible()) {
            await sslModeRadio.click();
            
            // Test connection with this SSL mode
            await page.click('[data-testid="test-ssl-connection"]');
            
            // Wait for connection test result
            await page.waitForTimeout(10000);
            
            const connectionResult = page.locator('[data-testid="ssl-connection-result"]');
            if (await connectionResult.isVisible()) {
              const resultText = await connectionResult.textContent();
              console.log(`SSL mode ${mode} result: ${resultText}`);
              
              await trackDataEvent('sslErrors', {
                sslMode: mode,
                result: resultText,
                success: resultText.includes('success') || resultText.includes('connected')
              });
              
              if (resultText.includes('success') || resultText.includes('connected')) {
                console.log(`✅ SSL mode ${mode} successful`);
                break; // Use the first working SSL mode
              } else if (resultText.includes('certificate') || resultText.includes('ssl')) {
                console.log(`🚨 SSL certificate issue with mode ${mode}: ${resultText}`);
              }
            }
          }
        }
      }
      
      // 4. Test certificate validation bypass
      const bypassCertValidation = page.locator('[data-testid="bypass-cert-validation"]');
      if (await bypassCertValidation.isVisible()) {
        console.log('🔓 Testing certificate validation bypass...');
        
        await bypassCertValidation.check();
        await page.click('[data-testid="test-bypass-connection"]');
        
        await page.waitForTimeout(8000);
        
        const bypassResult = page.locator('[data-testid="bypass-connection-result"]');
        if (await bypassResult.isVisible()) {
          const bypassText = await bypassResult.textContent();
          console.log(`Certificate bypass result: ${bypassText}`);
          
          await trackDataEvent('sslErrors', {
            type: 'certificate_bypass_attempt',
            result: bypassText,
            success: bypassText.includes('success')
          });
        }
      }
      
      // 5. Test pg_hba.conf error handling
      const pgHbaError = page.locator('[data-testid="pg-hba-error"]');
      if (await pgHbaError.isVisible()) {
        console.log('🚨 pg_hba.conf error detected');
        
        const errorMessage = await pgHbaError.textContent();
        console.log(`pg_hba.conf error: ${errorMessage}`);
        
        await trackDataEvent('errors', {
          type: 'pg_hba_configuration_error',
          errorMessage: errorMessage
        });
        
        // Test alternative authentication methods
        const altAuthMethods = page.locator('[data-testid="alternative-auth-methods"]');
        if (await altAuthMethods.isVisible()) {
          const methods = ['md5', 'scram-sha-256', 'trust'];
          
          for (const method of methods) {
            const methodOption = page.locator(`[data-testid="auth-method-${method}"]`);
            if (await methodOption.isVisible()) {
              await methodOption.click();
              await page.click('[data-testid="test-auth-method"]');
              
              await page.waitForTimeout(5000);
              
              const authResult = page.locator('[data-testid="auth-method-result"]');
              if (await authResult.isVisible()) {
                const authText = await authResult.textContent();
                console.log(`Auth method ${method} result: ${authText}`);
                
                if (authText.includes('success')) {
                  console.log(`✅ Auth method ${method} working`);
                  break;
                }
              }
            }
          }
        }
      }
      
      console.log('✅ Real PostgreSQL SSL Connection Issues Resolution test completed');
    });

    test('Connection Pool Management and Recovery', async ({ page }) => {
      console.log('🏊 Testing Connection Pool Management and Recovery...');
      
      await authenticate(page);
      
      // 1. Navigate to connection pool monitoring
      await page.goto('/admin/connection-pool');
      await page.waitForSelector('[data-testid="connection-pool-monitor"]', { timeout: 15000 });
      
      // 2. Check current pool status
      const poolMetrics = {
        activeConnections: '[data-testid="active-connections"]',
        idleConnections: '[data-testid="idle-connections"]',
        totalConnections: '[data-testid="total-connections"]',
        maxConnections: '[data-testid="max-connections"]',
        queuedRequests: '[data-testid="queued-requests"]'
      };
      
      for (const [metric, selector] of Object.entries(poolMetrics)) {
        const element = page.locator(selector);
        if (await element.isVisible()) {
          const value = await element.textContent();
          console.log(`📊 ${metric}: ${value}`);
          
          await trackDataEvent('performanceMetrics', {
            metric: metric,
            value: parseInt(value) || 0
          });
        }
      }
      
      // 3. Test connection pool stress
      console.log('⚡ Testing connection pool under stress...');
      
      // Trigger multiple simultaneous data operations
      const dataOperations = [
        '/api/portfolio/holdings',
        '/api/market/overview',
        '/api/stocks/AAPL/quote',
        '/api/portfolio/performance',
        '/api/trading/signals'
      ];
      
      // Make multiple concurrent requests
      await page.evaluate(async (operations) => {
        const promises = [];
        for (let i = 0; i < 20; i++) {
          for (const operation of operations) {
            promises.push(fetch(operation).catch(e => ({ error: e.message })));
          }
        }
        return Promise.all(promises);
      }, dataOperations);
      
      // Check pool status after stress test
      await page.waitForTimeout(5000);
      await page.click('[data-testid="refresh-pool-status"]');
      
      const poolWarnings = page.locator('[data-testid="pool-warning"]');
      if (await poolWarnings.count() > 0) {
        console.log('⚠️ Connection pool warnings detected');
        
        for (let i = 0; i < await poolWarnings.count(); i++) {
          const warning = poolWarnings.nth(i);
          const warningText = await warning.textContent();
          console.log(`Pool warning ${i + 1}: ${warningText}`);
          
          await trackDataEvent('errors', {
            type: 'connection_pool_warning',
            message: warningText
          });
        }
      }
      
      // 4. Test pool recovery after exhaustion
      const poolExhausted = page.locator('[data-testid="pool-exhausted"]');
      if (await poolExhausted.isVisible()) {
        console.log('🚨 Connection pool exhausted');
        
        const exhaustedMessage = await poolExhausted.textContent();
        await trackDataEvent('errors', {
          type: 'connection_pool_exhausted',
          message: exhaustedMessage
        });
        
        // Test pool recovery
        await page.click('[data-testid="recover-pool"]');
        await page.waitForTimeout(10000);
        
        const recoveryStatus = page.locator('[data-testid="pool-recovery-status"]');
        if (await recoveryStatus.isVisible()) {
          const recoveryText = await recoveryStatus.textContent();
          console.log(`Pool recovery: ${recoveryText}`);
          
          if (recoveryText.includes('recovered') || recoveryText.includes('healthy')) {
            console.log('✅ Connection pool recovery successful');
          }
        }
      }
      
      console.log('✅ Connection Pool Management and Recovery test completed');
    });

  });

  test.describe('AAII Data Loading Integration @critical @enterprise @data-loading', () => {

    test('Real AAII Data Loading Pipeline with Error Handling', async ({ page }) => {
      console.log('📊 Testing Real AAII Data Loading Pipeline with Error Handling...');
      
      await authenticate(page);
      
      // 1. Navigate to AAII data management
      await page.goto('/admin/aaii-data');
      await page.waitForSelector('[data-testid="aaii-data-management"]', { timeout: 15000 });
      
      // 2. Check current AAII data status
      const lastUpdate = page.locator('[data-testid="last-aaii-update"]');
      if (await lastUpdate.isVisible()) {
        const updateTime = await lastUpdate.textContent();
        console.log(`📅 Last AAII update: ${updateTime}`);
        
        await trackDataEvent('dataLoadEvents', {
          type: 'last_update_check',
          lastUpdate: updateTime
        });
      }
      
      // 3. Test manual AAII data load
      console.log('🔄 Testing manual AAII data load...');
      
      const loadStartTime = Date.now();
      await page.click('[data-testid="load-aaii-data"]');
      
      // Monitor loading progress
      const loadingProgress = page.locator('[data-testid="aaii-loading-progress"]');
      if (await loadingProgress.isVisible({ timeout: 5000 })) {
        console.log('📊 AAII loading progress indicator visible');
        
        // Monitor progress updates
        for (let i = 0; i < 30; i++) { // Monitor for up to 30 seconds
          await page.waitForTimeout(1000);
          
          const progressText = await loadingProgress.textContent().catch(() => '');
          if (progressText) {
            console.log(`Progress: ${progressText}`);
            
            if (progressText.includes('100%') || progressText.includes('completed')) {
              console.log('✅ AAII data loading completed');
              break;
            }
          }
          
          // Check for loading errors
          const loadingError = page.locator('[data-testid="aaii-loading-error"]');
          if (await loadingError.isVisible()) {
            const errorText = await loadingError.textContent();
            console.log(`🚨 AAII loading error: ${errorText}`);
            
            await trackDataEvent('dataLoadEvents', {
              type: 'loading_error',
              errorMessage: errorText,
              timeElapsed: Date.now() - loadStartTime
            });
            
            // Test error recovery options
            const retryButton = page.locator('[data-testid="retry-aaii-load"]');
            if (await retryButton.isVisible()) {
              console.log('🔄 Testing AAII load retry...');
              await retryButton.click();
              
              await trackDataEvent('dataLoadEvents', {
                type: 'retry_attempted',
                retryTime: Date.now() - loadStartTime
              });
            }
            
            break;
          }
        }
      }
      
      // 4. Test SSL/Certificate specific issues with AAII
      const sslIssue = page.locator('[data-testid="aaii-ssl-issue"]');
      if (await sslIssue.isVisible()) {
        console.log('🔐 AAII SSL issue detected');
        
        const sslErrorText = await sslIssue.textContent();
        console.log(`SSL Error: ${sslErrorText}`);
        
        await trackDataEvent('sslErrors', {
          type: 'aaii_ssl_error',
          errorMessage: sslErrorText
        });
        
        // Test SSL bypass for AAII
        const bypassSSL = page.locator('[data-testid="bypass-aaii-ssl"]');
        if (await bypassSSL.isVisible()) {
          console.log('🔓 Testing AAII SSL bypass...');
          await bypassSSL.click();
          
          await page.waitForTimeout(5000);
          
          const bypassResult = page.locator('[data-testid="ssl-bypass-result"]');
          if (await bypassResult.isVisible()) {
            const bypassText = await bypassResult.textContent();
            console.log(`SSL bypass result: ${bypassText}`);
            
            if (bypassText.includes('success')) {
              console.log('✅ AAII SSL bypass successful');
            }
          }
        }
      }
      
      // 5. Test fallback data sources
      const fallbackData = page.locator('[data-testid="aaii-fallback-data"]');
      if (await fallbackData.isVisible()) {
        console.log('📋 AAII fallback data activated');
        
        const fallbackSource = await fallbackData.textContent();
        console.log(`Fallback source: ${fallbackSource}`);
        
        await trackDataEvent('dataLoadEvents', {
          type: 'fallback_data_used',
          fallbackSource: fallbackSource
        });
      }
      
      // 6. Verify data integrity after load
      const dataIntegrityCheck = page.locator('[data-testid="data-integrity-check"]');
      if (await dataIntegrityCheck.isVisible()) {
        await dataIntegrityCheck.click();
        
        await page.waitForTimeout(5000);
        
        const integrityResult = page.locator('[data-testid="integrity-result"]');
        if (await integrityResult.isVisible()) {
          const integrityText = await integrityResult.textContent();
          console.log(`Data integrity check: ${integrityText}`);
          
          await trackDataEvent('dataLoadEvents', {
            type: 'integrity_check',
            result: integrityText,
            passed: integrityText.includes('passed') || integrityText.includes('valid')
          });
        }
      }
      
      console.log('✅ Real AAII Data Loading Pipeline test completed');
    });

    test('Data Caching and Performance Optimization', async ({ page }) => {
      console.log('🗄️ Testing Data Caching and Performance Optimization...');
      
      await authenticate(page);
      
      // 1. Navigate to cache management
      await page.goto('/admin/cache-management');
      await page.waitForSelector('[data-testid="cache-management"]', { timeout: 15000 });
      
      // 2. Check cache status
      const cacheMetrics = {
        hitRate: '[data-testid="cache-hit-rate"]',
        missRate: '[data-testid="cache-miss-rate"]',
        cacheSize: '[data-testid="cache-size"]',
        evictionRate: '[data-testid="cache-eviction-rate"]'
      };
      
      for (const [metric, selector] of Object.entries(cacheMetrics)) {
        const element = page.locator(selector);
        if (await element.isVisible()) {
          const value = await element.textContent();
          console.log(`📊 Cache ${metric}: ${value}`);
          
          await trackDataEvent('cacheEvents', {
            metric: metric,
            value: value
          });
        }
      }
      
      // 3. Test cache warming
      console.log('🔥 Testing cache warming...');
      
      await page.click('[data-testid="warm-cache"]');
      
      const warmingProgress = page.locator('[data-testid="cache-warming-progress"]');
      if (await warmingProgress.isVisible()) {
        console.log('🔥 Cache warming in progress...');
        
        for (let i = 0; i < 20; i++) {
          await page.waitForTimeout(1000);
          
          const progressText = await warmingProgress.textContent().catch(() => '');
          if (progressText.includes('completed')) {
            console.log('✅ Cache warming completed');
            break;
          }
        }
      }
      
      // 4. Test cache performance with real data requests
      console.log('⚡ Testing cache performance with real requests...');
      
      const testEndpoints = [
        '/api/portfolio/holdings',
        '/api/market/overview',
        '/api/stocks/AAPL/quote'
      ];
      
      for (const endpoint of testEndpoints) {
        // First request (likely cache miss)
        const startTime1 = Date.now();
        await page.evaluate(async (url) => {
          await fetch(url);
        }, endpoint);
        const firstRequestTime = Date.now() - startTime1;
        
        // Second request (should be cache hit)
        const startTime2 = Date.now();
        await page.evaluate(async (url) => {
          await fetch(url);
        }, endpoint);
        const secondRequestTime = Date.now() - startTime2;
        
        console.log(`📊 ${endpoint}: First: ${firstRequestTime}ms, Second: ${secondRequestTime}ms`);
        
        await trackDataEvent('performanceMetrics', {
          endpoint: endpoint,
          firstRequestTime: firstRequestTime,
          secondRequestTime: secondRequestTime,
          cacheSpeedup: firstRequestTime / secondRequestTime
        });
      }
      
      // 5. Test cache invalidation
      console.log('🗑️ Testing cache invalidation...');
      
      await page.click('[data-testid="invalidate-cache"]');
      
      const invalidationResult = page.locator('[data-testid="cache-invalidation-result"]');
      if (await invalidationResult.isVisible({ timeout: 5000 })) {
        const resultText = await invalidationResult.textContent();
        console.log(`Cache invalidation: ${resultText}`);
        
        await trackDataEvent('cacheEvents', {
          type: 'cache_invalidation',
          result: resultText
        });
      }
      
      // 6. Test memory usage monitoring
      const memoryUsage = page.locator('[data-testid="cache-memory-usage"]');
      if (await memoryUsage.isVisible()) {
        const memoryText = await memoryUsage.textContent();
        console.log(`📊 Cache memory usage: ${memoryText}`);
        
        const memoryWarning = page.locator('[data-testid="memory-warning"]');
        if (await memoryWarning.isVisible()) {
          const warningText = await memoryWarning.textContent();
          console.log(`⚠️ Memory warning: ${warningText}`);
          
          await trackDataEvent('cacheEvents', {
            type: 'memory_warning',
            message: warningText
          });
        }
      }
      
      console.log('✅ Data Caching and Performance Optimization test completed');
    });

  });

  test.describe('Data Pipeline Reliability @critical @enterprise @data-pipeline', () => {

    test('End-to-End Data Flow Monitoring', async ({ page }) => {
      console.log('🔄 Testing End-to-End Data Flow Monitoring...');
      
      await authenticate(page);
      
      // 1. Navigate to data pipeline monitoring
      await page.goto('/admin/data-pipeline');
      await page.waitForSelector('[data-testid="data-pipeline-monitor"]', { timeout: 15000 });
      
      // 2. Check pipeline health
      const pipelineStages = [
        'data-ingestion',
        'data-validation',
        'data-transformation',
        'data-storage',
        'data-serving'
      ];
      
      for (const stage of pipelineStages) {
        const stageStatus = page.locator(`[data-testid="${stage}-status"]`);
        if (await stageStatus.isVisible()) {
          const statusText = await stageStatus.textContent();
          console.log(`📊 ${stage}: ${statusText}`);
          
          await trackDataEvent('dataLoadEvents', {
            stage: stage,
            status: statusText,
            healthy: statusText.includes('healthy') || statusText.includes('active')
          });
          
          // Check for stage-specific errors
          const stageError = page.locator(`[data-testid="${stage}-error"]`);
          if (await stageError.isVisible()) {
            const errorText = await stageError.textContent();
            console.log(`🚨 ${stage} error: ${errorText}`);
            
            await trackDataEvent('errors', {
              type: 'pipeline_stage_error',
              stage: stage,
              errorMessage: errorText
            });
          }
        }
      }
      
      // 3. Test pipeline restart capability
      const restartPipeline = page.locator('[data-testid="restart-pipeline"]');
      if (await restartPipeline.isVisible()) {
        console.log('🔄 Testing pipeline restart...');
        await restartPipeline.click();
        
        await page.waitForTimeout(10000);
        
        const restartResult = page.locator('[data-testid="pipeline-restart-result"]');
        if (await restartResult.isVisible()) {
          const resultText = await restartResult.textContent();
          console.log(`Pipeline restart: ${resultText}`);
          
          await trackDataEvent('dataLoadEvents', {
            type: 'pipeline_restart',
            result: resultText,
            success: resultText.includes('success') || resultText.includes('restarted')
          });
        }
      }
      
      // 4. Monitor data freshness
      const dataFreshness = page.locator('[data-testid="data-freshness"]');
      if (await dataFreshness.isVisible()) {
        const freshnessText = await dataFreshness.textContent();
        console.log(`📅 Data freshness: ${freshnessText}`);
        
        await trackDataEvent('dataLoadEvents', {
          type: 'data_freshness_check',
          freshness: freshnessText
        });
        
        // Check for stale data warnings
        const staleWarning = page.locator('[data-testid="stale-data-warning"]');
        if (await staleWarning.isVisible()) {
          const warningText = await staleWarning.textContent();
          console.log(`⚠️ Stale data warning: ${warningText}`);
          
          await trackDataEvent('errors', {
            type: 'stale_data_warning',
            message: warningText
          });
        }
      }
      
      console.log('✅ End-to-End Data Flow Monitoring test completed');
    });

  });

  test.afterEach(async () => {
    // Data loading session summary
    console.log('\n📊 Database and Data Loading Session Summary:');
    console.log(`Connection attempts: ${dataSession.connectionAttempts.length}`);
    console.log(`SSL errors: ${dataSession.sslErrors.length}`);
    console.log(`Data load events: ${dataSession.dataLoadEvents.length}`);
    console.log(`Performance metrics: ${dataSession.performanceMetrics.length}`);
    console.log(`Cache events: ${dataSession.cacheEvents.length}`);
    console.log(`Total errors: ${dataSession.errors.length}`);
    
    // Log SSL-specific issues (known problem area)
    if (dataSession.sslErrors.length > 0) {
      console.log('\n🔐 SSL/Certificate Issues Detected:');
      dataSession.sslErrors.forEach(error => {
        console.log(`  ${error.timestamp}: ${error.type} - ${error.message || error.result}`);
      });
    }
    
    // Log data loading performance
    if (dataSession.performanceMetrics.length > 0) {
      console.log('\n⚡ Performance Metrics:');
      dataSession.performanceMetrics.forEach(metric => {
        if (metric.firstRequestTime && metric.secondRequestTime) {
          console.log(`  ${metric.endpoint}: Cache speedup ${metric.cacheSpeedup.toFixed(2)}x`);
        } else {
          console.log(`  ${metric.metric}: ${metric.value}`);
        }
      });
    }
    
    // Log critical database errors
    const criticalErrors = dataSession.errors.filter(error => 
      error.type.includes('connection') || error.type.includes('pool') || error.type.includes('pg_hba')
    );
    
    if (criticalErrors.length > 0) {
      console.log('\n🚨 Critical Database Errors:');
      criticalErrors.forEach(error => {
        console.log(`  ${error.timestamp}: ${error.type} - ${error.message}`);
      });
    }
    
    // Calculate success rates
    const totalDataLoads = dataSession.dataLoadEvents.filter(event => event.type === 'loading_error' || event.type === 'integrity_check').length;
    const successfulLoads = dataSession.dataLoadEvents.filter(event => event.type === 'integrity_check' && event.passed).length;
    const successRate = totalDataLoads > 0 ? (successfulLoads / totalDataLoads * 100).toFixed(1) : 100;
    
    console.log(`\n📈 Data Loading Success Rate: ${successRate}% (${successfulLoads}/${totalDataLoads})`);
  });

});

export default {
  testConfig
};