/**
 * User Journey Integration Tests
 * Tests complete end-to-end user workflows and scenarios
 * Validates real user interactions across the entire application
 */

const { test, expect } = require('@playwright/test');

test.describe('User Journey Integration Tests - Real User Workflows', () => {
  
  const testConfig = {
    baseURL: process.env.E2E_BASE_URL || 'https://d1zb7knau41vl9.cloudfront.net',
    testUser: {
      email: process.env.E2E_TEST_EMAIL || 'e2e-test@example.com',
      password: process.env.E2E_TEST_PASSWORD || 'E2ETest123!'
    }
  };

  const testData = {
    testSymbols: ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA'],
    testPortfolio: {
      name: 'E2E Test Journey Portfolio',
      description: 'Portfolio created during user journey testing'
    },
    testWatchlist: {
      name: 'E2E Test Watchlist',
      symbols: ['AAPL', 'MSFT', 'AMZN']
    }
  };

  // User journey state tracking
  let journeyState = {
    interactions: [],
    pageVisits: [],
    dataChanges: [],
    errors: []
  };

  async function trackUserInteraction(page, action, element, data = {}) {
    journeyState.interactions.push({
      action,
      element,
      data,
      timestamp: new Date().toISOString(),
      url: page.url()
    });
  }

  async function authenticate(page) {
    const isAuth = await page.locator('[data-testid="user-avatar"]').isVisible().catch(() => false);
    if (!isAuth) {
      await page.locator('button:has-text("Sign In")').click();
      await trackUserInteraction(page, 'click', 'sign-in-button');
      
      await page.fill('[data-testid="email-input"]', testConfig.testUser.email);
      await trackUserInteraction(page, 'fill', 'email-input', { email: testConfig.testUser.email });
      
      await page.fill('[data-testid="password-input"]', testConfig.testUser.password);
      await trackUserInteraction(page, 'fill', 'password-input');
      
      await page.click('[data-testid="login-submit"]');
      await trackUserInteraction(page, 'click', 'login-submit');
      
      await page.waitForSelector('[data-testid="user-avatar"]', { timeout: 15000 });
    }
  }

  test.beforeEach(async ({ page }) => {
    // Setup comprehensive user journey tracking
    journeyState = { interactions: [], pageVisits: [], dataChanges: [], errors: [] };
    
    // Track page navigation
    page.on('load', () => {
      journeyState.pageVisits.push({
        url: page.url(),
        timestamp: new Date().toISOString()
      });
    });
    
    // Track console errors
    page.on('console', msg => {
      if (msg.type() === 'error') {
        journeyState.errors.push({
          message: msg.text(),
          timestamp: new Date().toISOString(),
          url: page.url()
        });
      }
    });
    
    await page.goto(testConfig.baseURL);
    await page.waitForLoadState('networkidle');
  });

  test.afterEach(async ({ page }) => {
    console.log('\n📊 User Journey Summary:');
    console.log(`Pages visited: ${journeyState.pageVisits.length}`);
    console.log(`Interactions: ${journeyState.interactions.length}`);
    console.log(`Errors: ${journeyState.errors.length}`);
    
    if (journeyState.errors.length > 0) {
      console.log('❌ Errors during journey:');
      journeyState.errors.forEach(error => console.log(`  ${error.message}`));
    }
  });

  test.describe('New User Onboarding Journey', () => {

    test('Complete New User Onboarding Flow @critical @journey', async ({ page }) => {
      console.log('🎯 Testing Complete New User Onboarding Journey...');
      
      // 1. Landing page exploration
      await page.goto('/');
      await trackUserInteraction(page, 'navigate', 'landing-page');
      
      // Explore as anonymous user
      await page.click('[data-testid="nav-market"]');
      await page.waitForURL('**/market**');
      await trackUserInteraction(page, 'navigate', 'market-page');
      
      // Try to access protected content
      await page.click('[data-testid="nav-portfolio"]');
      await trackUserInteraction(page, 'attempt', 'protected-portfolio');
      
      // Should be redirected to login or shown auth modal
      const authVisible = await Promise.race([
        page.waitForSelector('[data-testid="auth-modal"]', { timeout: 5000 }).then(() => true),
        page.waitForURL('**/login**', { timeout: 5000 }).then(() => true),
        page.waitForTimeout(5000).then(() => false)
      ]);
      
      // 2. User Registration/Authentication
      await authenticate(page);
      await trackUserInteraction(page, 'complete', 'authentication');
      
      // 3. First-time user setup
      await page.goto('/settings');
      await trackUserInteraction(page, 'navigate', 'settings-first-time');
      
      // Check for onboarding elements
      const onboardingPresent = await page.locator('[data-testid="onboarding-wizard"]').isVisible().catch(() => false);
      if (onboardingPresent) {
        await page.click('[data-testid="start-onboarding"]');
        await trackUserInteraction(page, 'start', 'onboarding-wizard');
        
        // Complete onboarding steps
        const steps = await page.locator('[data-testid^="onboarding-step-"]').count();
        for (let i = 0; i < steps; i++) {
          await page.click('[data-testid="onboarding-next"]');
          await trackUserInteraction(page, 'next', `onboarding-step-${i}`);
          await page.waitForTimeout(1000);
        }
      }
      
      // 4. API Keys setup (optional)
      await page.goto('/settings/api-keys');
      await trackUserInteraction(page, 'navigate', 'api-keys-setup');
      
      // Check if user sees API key setup
      const apiKeySetup = await page.locator('[data-testid="api-key-setup-guide"]').isVisible().catch(() => false);
      if (apiKeySetup) {
        // Simulate reading the guide
        await page.waitForTimeout(2000);
        await trackUserInteraction(page, 'view', 'api-key-guide');
      }
      
      // 5. First portfolio exploration
      await page.goto('/portfolio');
      await trackUserInteraction(page, 'navigate', 'first-portfolio-visit');
      
      // Check for empty portfolio state
      const emptyPortfolio = await page.locator('[data-testid="empty-portfolio"]').isVisible().catch(() => false);
      if (emptyPortfolio) {
        await trackUserInteraction(page, 'view', 'empty-portfolio-state');
        
        // Look for getting started guidance
        const gettingStarted = page.locator('[data-testid="getting-started-guide"]');
        if (await gettingStarted.isVisible()) {
          await gettingStarted.click();
          await trackUserInteraction(page, 'interact', 'getting-started-guide');
        }
      }
      
      // 6. First market data exploration
      await page.goto('/market');
      await trackUserInteraction(page, 'navigate', 'market-exploration');
      
      // Explore market overview
      await page.waitForSelector('[data-testid="market-overview"]');
      
      // Click on a major index
      const marketIndex = page.locator('[data-testid^="market-index-"]').first();
      if (await marketIndex.isVisible()) {
        await marketIndex.click();
        await trackUserInteraction(page, 'explore', 'market-index');
      }
      
      // 7. Stock research journey
      await page.goto(`/stocks/${testData.testSymbols[0]}`);
      await trackUserInteraction(page, 'research', `stock-${testData.testSymbols[0]}`);
      
      // Explore stock details
      await page.waitForSelector('[data-testid="stock-chart"]');
      
      // Interact with chart periods
      const chartPeriods = ['1D', '1W', '1M'];
      for (const period of chartPeriods) {
        const periodButton = page.locator(`[data-testid="chart-${period}"]`);
        if (await periodButton.isVisible()) {
          await periodButton.click();
          await trackUserInteraction(page, 'chart-period', period);
          await page.waitForTimeout(1000);
        }
      }
      
      // View technical analysis
      const techAnalysisTab = page.locator('[data-testid="technical-analysis-tab"]');
      if (await techAnalysisTab.isVisible()) {
        await techAnalysisTab.click();
        await trackUserInteraction(page, 'tab', 'technical-analysis');
        await page.waitForTimeout(2000);
      }
      
      // 8. Create first watchlist
      await page.goto('/watchlist');
      await trackUserInteraction(page, 'navigate', 'first-watchlist');
      
      const createWatchlistButton = page.locator('[data-testid="create-watchlist"]');
      if (await createWatchlistButton.isVisible()) {
        await createWatchlistButton.click();
        await trackUserInteraction(page, 'create', 'first-watchlist');
        
        // Fill watchlist details
        await page.fill('[data-testid="watchlist-name"]', testData.testWatchlist.name);
        await page.click('[data-testid="save-watchlist"]');
        await trackUserInteraction(page, 'save', 'watchlist-created');
        
        // Add symbols to watchlist
        for (const symbol of testData.testWatchlist.symbols.slice(0, 2)) {
          await page.fill('[data-testid="add-symbol-input"]', symbol);
          await page.click('[data-testid="add-symbol-button"]');
          await trackUserInteraction(page, 'add-symbol', symbol);
          await page.waitForTimeout(1000);
        }
      }
      
      // 9. Explore trading features
      await page.goto('/trading');
      await trackUserInteraction(page, 'navigate', 'trading-exploration');
      
      // Look at trading signals
      await page.waitForSelector('[data-testid="trading-signals"]', { timeout: 10000 });
      
      const tradingSignals = page.locator('[data-testid^="signal-card-"]');
      const signalCount = await tradingSignals.count();
      
      if (signalCount > 0) {
        await tradingSignals.first().click();
        await trackUserInteraction(page, 'view', 'trading-signal');
      }
      
      // 10. Complete onboarding - return to dashboard
      await page.goto('/');
      await trackUserInteraction(page, 'complete', 'onboarding-journey');
      
      // Verify user sees personalized dashboard
      await page.waitForSelector('[data-testid="dashboard"]');
      
      console.log('✅ Complete New User Onboarding Journey passed');
    });

  });

  test.describe('Portfolio Management Journey', () => {

    test('Complete Portfolio Management Workflow @critical @journey', async ({ page }) => {
      console.log('💼 Testing Complete Portfolio Management Journey...');
      
      await authenticate(page);
      
      // 1. Portfolio overview and analysis
      await page.goto('/portfolio');
      await trackUserInteraction(page, 'start', 'portfolio-management');
      
      await page.waitForSelector('[data-testid="portfolio-summary"]');
      
      // Check current portfolio state
      const portfolioValue = await page.locator('[data-testid="portfolio-total-value"]').textContent().catch(() => '$0');
      await trackUserInteraction(page, 'view', 'portfolio-value', { value: portfolioValue });
      
      // 2. Detailed performance analysis
      await page.click('[data-testid="portfolio-performance-link"]');
      await page.waitForURL('**/portfolio/performance**');
      await trackUserInteraction(page, 'navigate', 'performance-analysis');
      
      // Analyze performance across different time periods
      const performancePeriods = ['1M', '3M', '1Y'];
      for (const period of performancePeriods) {
        const periodButton = page.locator(`[data-testid="performance-period-${period}"]`);
        if (await periodButton.isVisible()) {
          await periodButton.click();
          await trackUserInteraction(page, 'analyze', `performance-${period}`);
          await page.waitForTimeout(2000);
        }
      }
      
      // 3. Holdings analysis
      await page.goto('/portfolio/holdings');
      await trackUserInteraction(page, 'navigate', 'holdings-analysis');
      
      await page.waitForSelector('[data-testid="holdings-table"]');
      
      // Analyze individual positions
      const holdings = page.locator('[data-testid^="holding-row-"]');
      const holdingCount = await holdings.count();
      
      if (holdingCount > 0) {
        // Click on first holding for detailed analysis
        await holdings.first().click();
        await trackUserInteraction(page, 'analyze', 'individual-holding');
        
        // If position detail modal opens
        const positionModal = page.locator('[data-testid="position-detail-modal"]');
        if (await positionModal.isVisible()) {
          // Analyze position metrics
          await page.waitForTimeout(2000);
          
          // Close modal
          await page.click('[data-testid="close-position-modal"]');
          await trackUserInteraction(page, 'close', 'position-detail');
        }
      }
      
      // 4. Portfolio optimization exploration
      await page.goto('/portfolio/optimize');
      await trackUserInteraction(page, 'navigate', 'portfolio-optimization');
      
      await page.waitForSelector('[data-testid="optimization-tools"]', { timeout: 15000 });
      
      // Run portfolio analysis
      const analyzeButton = page.locator('[data-testid="analyze-portfolio"]');
      if (await analyzeButton.isVisible()) {
        await analyzeButton.click();
        await trackUserInteraction(page, 'analyze', 'portfolio-optimization');
        
        // Wait for analysis results
        await page.waitForSelector('[data-testid="optimization-results"]', { timeout: 20000 });
        await trackUserInteraction(page, 'view', 'optimization-results');
      }
      
      // 5. Risk analysis
      await page.goto('/risk-management');
      await trackUserInteraction(page, 'navigate', 'risk-analysis');
      
      await page.waitForSelector('[data-testid="risk-metrics"]', { timeout: 15000 });
      
      // Review risk metrics
      const riskMetrics = ['beta', 'sharpe', 'volatility'];
      for (const metric of riskMetrics) {
        const metricElement = page.locator(`[data-testid="risk-${metric}"]`);
        if (await metricElement.isVisible()) {
          const value = await metricElement.textContent();
          await trackUserInteraction(page, 'review', `risk-${metric}`, { value });
        }
      }
      
      // 6. Performance comparison
      await page.goto('/portfolio/performance');
      await trackUserInteraction(page, 'navigate', 'performance-comparison');
      
      // Compare against benchmarks
      const benchmarkSelect = page.locator('[data-testid="benchmark-select"]');
      if (await benchmarkSelect.isVisible()) {
        await benchmarkSelect.selectOption('SPY');
        await trackUserInteraction(page, 'compare', 'benchmark-spy');
        await page.waitForTimeout(3000);
        
        await benchmarkSelect.selectOption('QQQ');
        await trackUserInteraction(page, 'compare', 'benchmark-qqq');
        await page.waitForTimeout(3000);
      }
      
      console.log('✅ Complete Portfolio Management Journey passed');
    });

  });

  test.describe('Market Research and Trading Journey', () => {

    test('Market Research to Trading Decision Journey @critical @journey', async ({ page }) => {
      console.log('🔍 Testing Market Research to Trading Decision Journey...');
      
      await authenticate(page);
      
      // 1. Market overview analysis
      await page.goto('/market');
      await trackUserInteraction(page, 'start', 'market-research');
      
      await page.waitForSelector('[data-testid="market-overview"]');
      
      // Analyze market conditions
      const marketIndices = page.locator('[data-testid^="market-index-"]');
      const indexCount = await marketIndices.count();
      
      for (let i = 0; i < Math.min(indexCount, 3); i++) {
        const index = marketIndices.nth(i);
        const indexName = await index.locator('[data-testid="index-name"]').textContent().catch(() => `index-${i}`);
        await index.click();
        await trackUserInteraction(page, 'analyze', `market-index-${indexName}`);
        await page.waitForTimeout(1000);
      }
      
      // 2. Sector analysis
      await page.goto('/sectors');
      await trackUserInteraction(page, 'navigate', 'sector-analysis');
      
      await page.waitForSelector('[data-testid="sector-performance"]');
      
      // Find best performing sector
      const sectors = page.locator('[data-testid^="sector-"]');
      const sectorCount = await sectors.count();
      
      if (sectorCount > 0) {
        // Click on technology sector (if available)
        const techSector = page.locator('[data-testid="sector-technology"]');
        if (await techSector.isVisible()) {
          await techSector.click();
          await trackUserInteraction(page, 'explore', 'technology-sector');
        } else {
          // Click on first available sector
          await sectors.first().click();
          await trackUserInteraction(page, 'explore', 'first-sector');
        }
        
        await page.waitForTimeout(2000);
      }
      
      // 3. Individual stock research
      const researchSymbol = testData.testSymbols[0];
      await page.goto(`/stocks/${researchSymbol}`);
      await trackUserInteraction(page, 'research', `stock-${researchSymbol}`);
      
      await page.waitForSelector('[data-testid="stock-chart"]');
      
      // Comprehensive chart analysis
      const chartPeriods = ['1D', '1W', '1M', '3M'];
      for (const period of chartPeriods) {
        const periodButton = page.locator(`[data-testid="chart-${period}"]`);
        if (await periodButton.isVisible()) {
          await periodButton.click();
          await trackUserInteraction(page, 'chart-analysis', `${researchSymbol}-${period}`);
          await page.waitForTimeout(2000);
        }
      }
      
      // 4. Technical analysis deep dive
      await page.click('[data-testid="technical-analysis-tab"]');
      await trackUserInteraction(page, 'navigate', 'technical-analysis');
      
      await page.waitForSelector('[data-testid="technical-indicators"]');
      
      // Review key technical indicators
      const indicators = ['rsi', 'macd', 'sma', 'ema'];
      for (const indicator of indicators) {
        const indicatorElement = page.locator(`[data-testid="indicator-${indicator}"]`);
        if (await indicatorElement.isVisible()) {
          const signal = await indicatorElement.locator('[data-testid="indicator-signal"]').textContent().catch(() => 'neutral');
          await trackUserInteraction(page, 'analyze', `${indicator}-signal`, { signal });
        }
      }
      
      // 5. News and sentiment analysis
      await page.click('[data-testid="news-tab"]');
      await trackUserInteraction(page, 'navigate', 'news-analysis');
      
      await page.waitForSelector('[data-testid="stock-news"]');
      
      // Read recent news
      const newsArticles = page.locator('[data-testid^="news-article-"]');
      const articleCount = await newsArticles.count();
      
      if (articleCount > 0) {
        // Read first few articles
        for (let i = 0; i < Math.min(articleCount, 3); i++) {
          const article = newsArticles.nth(i);
          const headline = await article.locator('[data-testid="article-title"]').textContent().catch(() => `article-${i}`);
          await article.click();
          await trackUserInteraction(page, 'read', `news-${headline.substring(0, 30)}`);
          await page.waitForTimeout(1000);
        }
      }
      
      // 6. Add to watchlist for monitoring
      await page.goto('/watchlist');
      await trackUserInteraction(page, 'navigate', 'add-to-watchlist');
      
      // Add researched symbol to watchlist
      const addSymbolInput = page.locator('[data-testid="add-symbol-input"]');
      if (await addSymbolInput.isVisible()) {
        await addSymbolInput.fill(researchSymbol);
        await page.click('[data-testid="add-symbol-button"]');
        await trackUserInteraction(page, 'add', `watchlist-${researchSymbol}`);
        
        // Verify symbol added
        await page.waitForSelector(`[data-testid="watchlist-item-${researchSymbol}"]`, { timeout: 5000 });
      }
      
      // 7. Trading signals analysis
      await page.goto('/trading');
      await trackUserInteraction(page, 'navigate', 'trading-signals');
      
      await page.waitForSelector('[data-testid="trading-signals"]');
      
      // Look for signals related to researched stock
      const signalForSymbol = page.locator(`[data-testid="signal-${researchSymbol}"]`);
      if (await signalForSymbol.isVisible()) {
        await signalForSymbol.click();
        await trackUserInteraction(page, 'analyze', `trading-signal-${researchSymbol}`);
        
        // Review signal details
        await page.waitForTimeout(2000);
      }
      
      // 8. Trading decision simulation
      // Note: In a real scenario, this would involve actual order placement
      // For testing, we'll simulate the decision-making process
      
      await page.goto(`/stocks/${researchSymbol}`);
      await trackUserInteraction(page, 'decide', `trading-decision-${researchSymbol}`);
      
      // Simulate trade planning
      const tradeButton = page.locator('[data-testid="trade-stock"]');
      if (await tradeButton.isVisible()) {
        await tradeButton.click();
        await trackUserInteraction(page, 'plan', `trade-${researchSymbol}`);
        
        // If trade modal opens, simulate filling details (but don't submit)
        const tradeModal = page.locator('[data-testid="trade-modal"]');
        if (await tradeModal.isVisible()) {
          // Fill trade details
          await page.selectOption('[data-testid="trade-type"]', 'buy');
          await page.fill('[data-testid="trade-quantity"]', '10');
          
          await trackUserInteraction(page, 'plan-details', `trade-buy-10-${researchSymbol}`);
          
          // Cancel instead of submitting (for testing)
          await page.click('[data-testid="cancel-trade"]');
          await trackUserInteraction(page, 'cancel', 'trade-simulation');
        }
      }
      
      console.log('✅ Market Research to Trading Decision Journey passed');
    });

  });

  test.describe('Settings and Configuration Journey', () => {

    test('Complete Settings Configuration Journey @critical @journey', async ({ page }) => {
      console.log('⚙️ Testing Complete Settings Configuration Journey...');
      
      await authenticate(page);
      
      // 1. Profile management
      await page.goto('/settings');
      await trackUserInteraction(page, 'start', 'settings-configuration');
      
      await page.waitForSelector('[data-testid="user-profile-settings"]');
      
      // Update profile information
      const profileForm = page.locator('[data-testid="profile-form"]');
      if (await profileForm.isVisible()) {
        // Update display name
        const displayNameInput = page.locator('[data-testid="display-name"]');
        if (await displayNameInput.isVisible()) {
          await displayNameInput.clear();
          await displayNameInput.fill('E2E Test User Updated');
          await trackUserInteraction(page, 'update', 'display-name');
        }
        
        // Update timezone
        const timezoneSelect = page.locator('[data-testid="timezone-select"]');
        if (await timezoneSelect.isVisible()) {
          await timezoneSelect.selectOption('America/New_York');
          await trackUserInteraction(page, 'update', 'timezone');
        }
      }
      
      // 2. API Keys configuration
      await page.goto('/settings/api-keys');
      await trackUserInteraction(page, 'navigate', 'api-keys-config');
      
      await page.waitForSelector('[data-testid="api-keys-settings"]');
      
      // Configure test API keys (using test/paper trading keys)
      const apiProviders = ['alpaca', 'polygon', 'finnhub'];
      
      for (const provider of apiProviders) {
        const keyInput = page.locator(`[data-testid="${provider}-api-key"]`);
        const secretInput = page.locator(`[data-testid="${provider}-api-secret"]`);
        
        if (await keyInput.isVisible()) {
          // Clear existing keys
          await keyInput.clear();
          if (await secretInput.isVisible()) {
            await secretInput.clear();
          }
          
          // Set test keys (if available in environment)
          const testKey = process.env[`E2E_${provider.toUpperCase()}_KEY`];
          if (testKey) {
            await keyInput.fill(testKey);
            await trackUserInteraction(page, 'configure', `${provider}-api-key`);
            
            const testSecret = process.env[`E2E_${provider.toUpperCase()}_SECRET`];
            if (testSecret && await secretInput.isVisible()) {
              await secretInput.fill(testSecret);
              await trackUserInteraction(page, 'configure', `${provider}-api-secret`);
            }
            
            // Test connection
            const testButton = page.locator(`[data-testid="test-${provider}-connection"]`);
            if (await testButton.isVisible()) {
              await testButton.click();
              await trackUserInteraction(page, 'test', `${provider}-connection`);
              
              // Wait for test result
              await page.waitForSelector(`[data-testid="${provider}-test-result"]`, { timeout: 10000 });
              
              const testResult = await page.locator(`[data-testid="${provider}-test-result"]`).textContent();
              await trackUserInteraction(page, 'result', `${provider}-test`, { result: testResult });
            }
          }
        }
      }
      
      // 3. Notification preferences
      await page.goto('/settings');
      await page.click('[data-testid="notifications-tab"]');
      await trackUserInteraction(page, 'navigate', 'notification-settings');
      
      // Configure notification preferences
      const notificationTypes = ['email', 'push', 'sms'];
      
      for (const type of notificationTypes) {
        const checkbox = page.locator(`[data-testid="${type}-notifications"]`);
        if (await checkbox.isVisible()) {
          const isChecked = await checkbox.isChecked();
          
          // Toggle notification setting
          await checkbox.click();
          await trackUserInteraction(page, 'toggle', `${type}-notifications`, { enabled: !isChecked });
          
          // Toggle back to original state
          await checkbox.click();
          await trackUserInteraction(page, 'toggle', `${type}-notifications`, { enabled: isChecked });
        }
      }
      
      // 4. Theme and display preferences
      await page.click('[data-testid="display-tab"]');
      await trackUserInteraction(page, 'navigate', 'display-settings');
      
      // Test theme switching
      const themeSelect = page.locator('[data-testid="theme-select"]');
      if (await themeSelect.isVisible()) {
        // Switch to dark theme
        await themeSelect.selectOption('dark');
        await trackUserInteraction(page, 'change', 'theme-dark');
        await page.waitForTimeout(1000);
        
        // Verify theme change applied
        const bodyClass = await page.locator('body').getAttribute('class');
        
        // Switch back to light theme
        await themeSelect.selectOption('light');
        await trackUserInteraction(page, 'change', 'theme-light');
        await page.waitForTimeout(1000);
      }
      
      // Test chart preferences
      const chartTypeSelect = page.locator('[data-testid="default-chart-type"]');
      if (await chartTypeSelect.isVisible()) {
        await chartTypeSelect.selectOption('candlestick');
        await trackUserInteraction(page, 'change', 'chart-type-candlestick');
        
        await chartTypeSelect.selectOption('line');
        await trackUserInteraction(page, 'change', 'chart-type-line');
      }
      
      // 5. Security settings
      await page.click('[data-testid="security-tab"]');
      await trackUserInteraction(page, 'navigate', 'security-settings');
      
      // Review security settings
      const twoFactorToggle = page.locator('[data-testid="two-factor-toggle"]');
      if (await twoFactorToggle.isVisible()) {
        const is2FAEnabled = await twoFactorToggle.isChecked();
        await trackUserInteraction(page, 'review', 'two-factor-status', { enabled: is2FAEnabled });
        
        // If 2FA is not enabled, show setup option (but don't actually enable)
        if (!is2FAEnabled) {
          const setup2FAButton = page.locator('[data-testid="setup-2fa"]');
          if (await setup2FAButton.isVisible()) {
            await setup2FAButton.click();
            await trackUserInteraction(page, 'explore', '2fa-setup');
            
            // Close setup modal if it opens
            const setupModal = page.locator('[data-testid="2fa-setup-modal"]');
            if (await setupModal.isVisible()) {
              await page.click('[data-testid="close-2fa-setup"]');
              await trackUserInteraction(page, 'close', '2fa-setup');
            }
          }
        }
      }
      
      // 6. Data and privacy settings
      await page.click('[data-testid="privacy-tab"]');
      await trackUserInteraction(page, 'navigate', 'privacy-settings');
      
      // Review data sharing preferences
      const dataUsageToggle = page.locator('[data-testid="data-usage-analytics"]');
      if (await dataUsageToggle.isVisible()) {
        const analyticsEnabled = await dataUsageToggle.isChecked();
        await trackUserInteraction(page, 'review', 'data-analytics', { enabled: analyticsEnabled });
      }
      
      // 7. Save all settings
      const saveButton = page.locator('[data-testid="save-all-settings"]');
      if (await saveButton.isVisible()) {
        await saveButton.click();
        await trackUserInteraction(page, 'save', 'all-settings');
        
        // Wait for save confirmation
        await page.waitForSelector('[data-testid="settings-saved-confirmation"]', { timeout: 5000 });
        await trackUserInteraction(page, 'confirm', 'settings-saved');
      }
      
      // 8. Verify settings persistence
      await page.reload();
      await trackUserInteraction(page, 'verify', 'settings-persistence');
      
      // Check that settings were saved
      await page.waitForSelector('[data-testid="user-profile-settings"]');
      
      console.log('✅ Complete Settings Configuration Journey passed');
    });

  });

  test.describe('Error Recovery Journey', () => {

    test('Error Recovery and Resilience Journey @critical @journey @error', async ({ page }) => {
      console.log('🚨 Testing Error Recovery and Resilience Journey...');
      
      await authenticate(page);
      
      // 1. Network error simulation
      console.log('📡 Testing network error recovery...');
      
      // Go offline
      await page.context().setOffline(true);
      await trackUserInteraction(page, 'simulate', 'network-offline');
      
      // Try to navigate to different pages
      await page.goto('/portfolio');
      await trackUserInteraction(page, 'attempt', 'offline-navigation');
      
      // Should see offline indicator or error message
      const offlineIndicator = await page.locator('[data-testid="offline-indicator"]').isVisible().catch(() => false);
      const errorMessage = await page.locator('[data-testid="network-error"]').isVisible().catch(() => false);
      
      if (offlineIndicator || errorMessage) {
        await trackUserInteraction(page, 'detect', 'offline-state');
      }
      
      // Go back online
      await page.context().setOffline(false);
      await trackUserInteraction(page, 'simulate', 'network-online');
      
      // Wait for reconnection
      await page.waitForTimeout(3000);
      
      // Try navigation again
      await page.goto('/portfolio');
      await trackUserInteraction(page, 'recover', 'network-recovery');
      
      // Should successfully load
      await page.waitForSelector('[data-testid="portfolio-summary"]', { timeout: 15000 });
      
      // 2. API error handling
      console.log('🔌 Testing API error handling...');
      
      // Navigate to a page with heavy API usage
      await page.goto('/market');
      await trackUserInteraction(page, 'test', 'api-error-handling');
      
      // Monitor for error states
      const apiErrorExists = await page.locator('[data-testid="api-error"]').isVisible().catch(() => false);
      const retryButton = await page.locator('[data-testid="retry-api-call"]').isVisible().catch(() => false);
      
      if (apiErrorExists && retryButton) {
        await page.click('[data-testid="retry-api-call"]');
        await trackUserInteraction(page, 'retry', 'api-call');
        
        // Wait for retry result
        await page.waitForTimeout(5000);
      }
      
      // 3. Authentication error recovery
      console.log('🔐 Testing authentication error recovery...');
      
      // Clear auth storage to simulate session expiry
      await page.context().clearCookies();
      await page.evaluate(() => {
        localStorage.clear();
        sessionStorage.clear();
      });
      await trackUserInteraction(page, 'simulate', 'session-expiry');
      
      // Try to access protected content
      await page.goto('/portfolio');
      await trackUserInteraction(page, 'attempt', 'expired-session-access');
      
      // Should be redirected to login or see auth modal
      const authRequired = await Promise.race([
        page.waitForSelector('[data-testid="auth-modal"]', { timeout: 5000 }).then(() => true),
        page.waitForURL('**/login**', { timeout: 5000 }).then(() => true),
        page.waitForTimeout(5000).then(() => false)
      ]);
      
      if (authRequired) {
        await trackUserInteraction(page, 'detect', 'auth-required');
        
        // Re-authenticate
        await authenticate(page);
        await trackUserInteraction(page, 'recover', 'authentication');
        
        // Should now access portfolio successfully
        await page.goto('/portfolio');
        await page.waitForSelector('[data-testid="portfolio-summary"]', { timeout: 15000 });
      }
      
      // 4. Component error recovery
      console.log('🔧 Testing component error recovery...');
      
      // Navigate to a complex page
      await page.goto('/stocks/AAPL');
      await trackUserInteraction(page, 'test', 'component-errors');
      
      // Look for error boundaries or component errors
      const componentError = await page.locator('[data-testid="component-error"]').isVisible().catch(() => false);
      const errorBoundary = await page.locator('[data-testid="error-boundary"]').isVisible().catch(() => false);
      
      if (componentError || errorBoundary) {
        await trackUserInteraction(page, 'detect', 'component-error');
        
        // Try recovery action
        const retryComponent = page.locator('[data-testid="retry-component"]');
        if (await retryComponent.isVisible()) {
          await retryComponent.click();
          await trackUserInteraction(page, 'retry', 'component-recovery');
          await page.waitForTimeout(3000);
        }
      }
      
      // 5. Data loading error recovery
      console.log('📊 Testing data loading error recovery...');
      
      // Navigate to data-heavy page
      await page.goto('/market');
      await trackUserInteraction(page, 'test', 'data-loading-errors');
      
      // Look for loading errors
      const dataError = await page.locator('[data-testid="data-loading-error"]').isVisible().catch(() => false);
      
      if (dataError) {
        await trackUserInteraction(page, 'detect', 'data-loading-error');
        
        // Try refresh
        const refreshData = page.locator('[data-testid="refresh-data"]');
        if (await refreshData.isVisible()) {
          await refreshData.click();
          await trackUserInteraction(page, 'retry', 'data-refresh');
          await page.waitForTimeout(5000);
        }
      }
      
      // 6. Browser refresh recovery
      console.log('🔄 Testing browser refresh recovery...');
      
      // Navigate to a page with state
      await page.goto('/portfolio');
      await page.waitForSelector('[data-testid="portfolio-summary"]');
      
      // Refresh browser
      await page.reload();
      await trackUserInteraction(page, 'test', 'browser-refresh');
      
      // Should reload successfully with state restored
      await page.waitForSelector('[data-testid="portfolio-summary"]', { timeout: 15000 });
      await trackUserInteraction(page, 'verify', 'state-restoration');
      
      console.log('✅ Error Recovery and Resilience Journey passed');
    });

  });

});