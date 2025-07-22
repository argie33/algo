/**
 * Comprehensive Portfolio Management Integration Tests
 * Tests complete portfolio workflows, performance tracking, and data consistency
 * Integrated into existing enterprise testing framework
 */

import { test, expect } from '@playwright/test';

const testConfig = {
  baseURL: process.env.E2E_BASE_URL || 'https://d1zb7knau41vl9.cloudfront.net',
  apiURL: process.env.E2E_API_URL || 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev',
  testUser: {
    email: process.env.E2E_TEST_EMAIL || 'e2e-test@example.com',
    password: process.env.E2E_TEST_PASSWORD || 'E2ETest123!'
  },
  testSymbols: ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'SPY', 'QQQ'],
  testPortfolio: {
    name: 'Enterprise Integration Test Portfolio',
    description: 'Portfolio created for comprehensive integration testing'
  },
  timeout: 45000
};

test.describe('Comprehensive Portfolio Management Integration - Enterprise Framework', () => {
  
  let portfolioSession = {
    portfolios: [],
    holdings: [],
    transactions: [],
    performance: [],
    alerts: [],
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

  async function trackPortfolioAction(actionType, data) {
    portfolioSession[actionType].push({
      ...data,
      timestamp: new Date().toISOString()
    });
  }

  async function getPortfolioValue(page) {
    const valueElement = page.locator('[data-testid="portfolio-total-value"]');
    if (await valueElement.isVisible()) {
      const valueText = await valueElement.textContent();
      return parseFloat(valueText.replace(/[^0-9.-]/g, ''));
    }
    return null;
  }

  test.beforeEach(async ({ page }) => {
    // Reset portfolio session tracking
    portfolioSession = {
      portfolios: [],
      holdings: [],
      transactions: [],
      performance: [],
      alerts: [],
      errors: []
    };
    
    // Setup portfolio-specific monitoring
    page.on('console', msg => {
      if (msg.type() === 'error' && msg.text().includes('portfolio')) {
        portfolioSession.errors.push({
          message: msg.text(),
          timestamp: new Date().toISOString()
        });
      }
    });

    await page.goto(testConfig.baseURL);
    await page.waitForLoadState('networkidle');
  });

  test.describe('Portfolio Creation and Management @critical @enterprise @portfolio', () => {

    test('Complete Portfolio Creation Workflow', async ({ page }) => {
      console.log('💼 Testing Complete Portfolio Creation Workflow...');
      
      await authenticate(page);
      
      // 1. Navigate to portfolio management
      await page.goto('/portfolio');
      await page.waitForSelector('[data-testid="portfolio-page"]', { timeout: 15000 });
      
      // 2. Create new portfolio
      await page.click('[data-testid="create-portfolio-button"]');
      await page.waitForSelector('[data-testid="portfolio-creation-form"]', { timeout: 10000 });
      
      // 3. Fill portfolio details
      await page.fill('[data-testid="portfolio-name"]', testConfig.testPortfolio.name);
      await page.fill('[data-testid="portfolio-description"]', testConfig.testPortfolio.description);
      await page.selectOption('[data-testid="portfolio-strategy"]', 'growth');
      await page.selectOption('[data-testid="risk-tolerance"]', 'moderate');
      await page.fill('[data-testid="initial-cash"]', '100000');
      
      // 4. Set portfolio goals
      await page.click('[data-testid="set-goals-tab"]');
      await page.fill('[data-testid="target-return"]', '15');
      await page.fill('[data-testid="time-horizon"]', '5');
      await page.selectOption('[data-testid="investment-style"]', 'balanced');
      
      // 5. Configure rebalancing
      await page.click('[data-testid="rebalancing-tab"]');
      await page.check('[data-testid="auto-rebalance"]');
      await page.selectOption('[data-testid="rebalance-frequency"]', 'quarterly');
      await page.fill('[data-testid="rebalance-threshold"]', '5');
      
      // 6. Submit portfolio creation
      await page.click('[data-testid="create-portfolio-submit"]');
      await page.waitForSelector('[data-testid="portfolio-created-confirmation"]', { timeout: 10000 });
      
      const portfolioId = await page.locator('[data-testid="new-portfolio-id"]').textContent();
      console.log(`✅ Portfolio created with ID: ${portfolioId}`);
      
      await trackPortfolioAction('portfolios', {
        id: portfolioId,
        name: testConfig.testPortfolio.name,
        action: 'created'
      });
      
      // 7. Verify portfolio appears in list
      await page.goto('/portfolio');
      await page.waitForSelector(`[data-testid="portfolio-card-${portfolioId}"]`, { timeout: 15000 });
      
      const portfolioCard = page.locator(`[data-testid="portfolio-card-${portfolioId}"]`);
      const displayedName = await portfolioCard.locator('[data-testid="portfolio-name"]').textContent();
      const displayedValue = await portfolioCard.locator('[data-testid="portfolio-value"]').textContent();
      
      expect(displayedName).toBe(testConfig.testPortfolio.name);
      expect(displayedValue).toContain('100,000');
      
      console.log('✅ Complete Portfolio Creation Workflow passed');
    });

    test('Portfolio Holdings Management Integration', async ({ page }) => {
      console.log('📊 Testing Portfolio Holdings Management Integration...');
      
      await authenticate(page);
      await page.goto('/portfolio');
      
      // 1. Select existing portfolio or create one
      let portfolioId;
      const existingPortfolios = page.locator('[data-testid^="portfolio-card-"]');
      const portfolioCount = await existingPortfolios.count();
      
      if (portfolioCount > 0) {
        // Use existing portfolio
        portfolioId = await existingPortfolios.first().getAttribute('data-testid');
        portfolioId = portfolioId.replace('portfolio-card-', '');
        await existingPortfolios.first().click();
      } else {
        // Create new portfolio for testing
        await page.click('[data-testid="create-portfolio-button"]');
        await page.fill('[data-testid="portfolio-name"]', 'Test Holdings Portfolio');
        await page.fill('[data-testid="initial-cash"]', '50000');
        await page.click('[data-testid="create-portfolio-submit"]');
        portfolioId = await page.locator('[data-testid="new-portfolio-id"]').textContent();
      }
      
      // 2. Navigate to portfolio holdings
      await page.goto(`/portfolio/${portfolioId}/holdings`);
      await page.waitForSelector('[data-testid="holdings-page"]', { timeout: 15000 });
      
      const initialValue = await getPortfolioValue(page);
      console.log(`💰 Initial Portfolio Value: $${initialValue}`);
      
      // 3. Add holdings to portfolio
      const testHoldings = [
        { symbol: 'AAPL', quantity: '10', price: '150.00' },
        { symbol: 'MSFT', quantity: '15', price: '300.00' },
        { symbol: 'GOOGL', quantity: '5', price: '120.00' }
      ];
      
      for (const holding of testHoldings) {
        await page.click('[data-testid="add-holding-button"]');
        await page.waitForSelector('[data-testid="add-holding-form"]', { timeout: 10000 });
        
        await page.fill('[data-testid="holding-symbol"]', holding.symbol);
        await page.fill('[data-testid="holding-quantity"]', holding.quantity);
        await page.fill('[data-testid="holding-price"]', holding.price);
        await page.selectOption('[data-testid="transaction-type"]', 'buy');
        
        await page.click('[data-testid="add-holding-submit"]');
        await page.waitForSelector('[data-testid="holding-added-confirmation"]', { timeout: 5000 });
        
        console.log(`➕ Added holding: ${holding.quantity} shares of ${holding.symbol} at $${holding.price}`);
        
        await trackPortfolioAction('holdings', {
          portfolioId,
          symbol: holding.symbol,
          quantity: holding.quantity,
          price: holding.price,
          action: 'added'
        });
      }
      
      // 4. Verify holdings appear in table
      await page.reload();
      await page.waitForSelector('[data-testid="holdings-table"]', { timeout: 15000 });
      
      for (const holding of testHoldings) {
        const holdingRow = page.locator(`[data-testid="holding-row-${holding.symbol}"]`);
        await expect(holdingRow).toBeVisible();
        
        const quantity = await holdingRow.locator('[data-testid="holding-quantity"]').textContent();
        const symbol = await holdingRow.locator('[data-testid="holding-symbol"]').textContent();
        
        expect(quantity).toContain(holding.quantity);
        expect(symbol).toBe(holding.symbol);
      }
      
      // 5. Test holdings modification
      const firstHolding = testHoldings[0];
      const holdingRow = page.locator(`[data-testid="holding-row-${firstHolding.symbol}"]`);
      
      await holdingRow.locator('[data-testid="edit-holding"]').click();
      await page.waitForSelector('[data-testid="edit-holding-form"]', { timeout: 10000 });
      
      await page.fill('[data-testid="new-quantity"]', '15');
      await page.click('[data-testid="update-holding-submit"]');
      await page.waitForSelector('[data-testid="holding-updated-confirmation"]', { timeout: 5000 });
      
      // 6. Verify portfolio value updated
      await page.reload();
      const updatedValue = await getPortfolioValue(page);
      console.log(`💰 Updated Portfolio Value: $${updatedValue}`);
      
      if (initialValue && updatedValue) {
        expect(updatedValue).not.toBe(initialValue);
      }
      
      console.log('✅ Portfolio Holdings Management Integration passed');
    });

  });

  test.describe('Portfolio Performance Analytics @critical @enterprise @portfolio', () => {

    test('Performance Tracking and Analytics Integration', async ({ page }) => {
      console.log('📈 Testing Performance Tracking and Analytics Integration...');
      
      await authenticate(page);
      
      // 1. Navigate to portfolio performance
      await page.goto('/portfolio/performance');
      await page.waitForSelector('[data-testid="performance-dashboard"]', { timeout: 15000 });
      
      // 2. Test performance metrics
      const performanceMetrics = {
        totalReturn: '[data-testid="total-return"]',
        dailyPnL: '[data-testid="daily-pnl"]',
        annualizedReturn: '[data-testid="annualized-return"]',
        sharpeRatio: '[data-testid="sharpe-ratio"]',
        maxDrawdown: '[data-testid="max-drawdown"]',
        volatility: '[data-testid="volatility"]'
      };
      
      for (const [metric, selector] of Object.entries(performanceMetrics)) {
        const element = page.locator(selector);
        if (await element.isVisible()) {
          const value = await element.textContent();
          console.log(`📊 ${metric}: ${value}`);
          
          await trackPortfolioAction('performance', {
            metric,
            value
          });
        }
      }
      
      // 3. Test performance chart interactions
      const chartPeriods = ['1D', '1W', '1M', '3M', '6M', '1Y', 'ALL'];
      
      for (const period of chartPeriods) {
        const periodButton = page.locator(`[data-testid="chart-period-${period}"]`);
        if (await periodButton.isVisible()) {
          await periodButton.click();
          await page.waitForTimeout(2000);
          
          // Verify chart updates
          await page.waitForSelector('[data-testid="performance-chart"]:not([data-loading="true"])', { timeout: 10000 });
          console.log(`📊 Performance chart updated for ${period} period`);
        }
      }
      
      // 4. Test benchmark comparison
      await page.click('[data-testid="compare-benchmark"]');
      await page.waitForSelector('[data-testid="benchmark-selection"]', { timeout: 10000 });
      
      const benchmarks = ['SPY', 'QQQ', 'VTI'];
      
      for (const benchmark of benchmarks) {
        await page.selectOption('[data-testid="benchmark-select"]', benchmark);
        await page.click('[data-testid="add-benchmark"]');
        await page.waitForTimeout(2000);
        
        // Verify benchmark appears in chart
        const benchmarkLine = page.locator(`[data-testid="benchmark-line-${benchmark}"]`);
        if (await benchmarkLine.isVisible()) {
          console.log(`📊 Benchmark ${benchmark} added to comparison`);
        }
      }
      
      // 5. Test performance attribution
      await page.goto('/portfolio/attribution');
      await page.waitForSelector('[data-testid="attribution-analysis"]', { timeout: 15000 });
      
      // Check sector attribution
      const sectorAttribution = page.locator('[data-testid="sector-attribution"]');
      if (await sectorAttribution.isVisible()) {
        const sectors = page.locator('[data-testid^="sector-contribution-"]');
        const sectorCount = await sectors.count();
        
        console.log(`📊 Sector Attribution: ${sectorCount} sectors analyzed`);
        
        for (let i = 0; i < Math.min(3, sectorCount); i++) {
          const sector = sectors.nth(i);
          const sectorName = await sector.locator('[data-testid="sector-name"]').textContent();
          const contribution = await sector.locator('[data-testid="sector-contribution"]').textContent();
          
          console.log(`  ${sectorName}: ${contribution} contribution`);
        }
      }
      
      // 6. Test security-level attribution
      const securityAttribution = page.locator('[data-testid="security-attribution"]');
      if (await securityAttribution.isVisible()) {
        const securities = page.locator('[data-testid^="security-contribution-"]');
        const securityCount = await securities.count();
        
        console.log(`📊 Security Attribution: ${securityCount} securities analyzed`);
        
        // Check top contributors
        const topContributors = securities.locator('[data-testid="positive-contributor"]');
        const topContributorCount = await topContributors.count();
        
        if (topContributorCount > 0) {
          const topContributor = topContributors.first();
          const symbol = await topContributor.locator('[data-testid="contributor-symbol"]').textContent();
          const contribution = await topContributor.locator('[data-testid="contributor-value"]').textContent();
          
          console.log(`🏆 Top Contributor: ${symbol} (${contribution})`);
        }
      }
      
      console.log('✅ Performance Tracking and Analytics Integration passed');
    });

    test('Risk Analytics and Monitoring Integration', async ({ page }) => {
      console.log('⚠️ Testing Risk Analytics and Monitoring Integration...');
      
      await authenticate(page);
      
      // 1. Navigate to risk analytics
      await page.goto('/portfolio/risk');
      await page.waitForSelector('[data-testid="risk-dashboard"]', { timeout: 15000 });
      
      // 2. Test risk metrics
      const riskMetrics = {
        valueAtRisk: '[data-testid="value-at-risk"]',
        expectedShortfall: '[data-testid="expected-shortfall"]',
        beta: '[data-testid="portfolio-beta"]',
        correlation: '[data-testid="market-correlation"]',
        concentrationRisk: '[data-testid="concentration-risk"]'
      };
      
      for (const [metric, selector] of Object.entries(riskMetrics)) {
        const element = page.locator(selector);
        if (await element.isVisible()) {
          const value = await element.textContent();
          console.log(`⚠️ ${metric}: ${value}`);
        }
      }
      
      // 3. Test risk scenario analysis
      await page.click('[data-testid="scenario-analysis"]');
      await page.waitForSelector('[data-testid="scenario-form"]', { timeout: 10000 });
      
      const scenarios = [
        { name: 'Market Crash', marketMove: '-20', volatilityChange: '50' },
        { name: 'Bull Market', marketMove: '15', volatilityChange: '-10' },
        { name: 'High Volatility', marketMove: '0', volatilityChange: '100' }
      ];
      
      for (const scenario of scenarios) {
        await page.fill('[data-testid="scenario-name"]', scenario.name);
        await page.fill('[data-testid="market-move"]', scenario.marketMove);
        await page.fill('[data-testid="volatility-change"]', scenario.volatilityChange);
        
        await page.click('[data-testid="run-scenario"]');
        await page.waitForSelector('[data-testid="scenario-results"]', { timeout: 10000 });
        
        const portfolioImpact = await page.locator('[data-testid="portfolio-impact"]').textContent();
        console.log(`📊 ${scenario.name} Scenario Impact: ${portfolioImpact}`);
        
        await page.click('[data-testid="clear-scenario"]');
      }
      
      // 4. Test correlation analysis
      await page.goto('/portfolio/correlations');
      await page.waitForSelector('[data-testid="correlation-matrix"]', { timeout: 15000 });
      
      // Check correlation heatmap
      const correlationCells = page.locator('[data-testid^="correlation-cell-"]');
      const cellCount = await correlationCells.count();
      
      console.log(`🔄 Correlation Matrix: ${cellCount} correlation pairs`);
      
      if (cellCount > 0) {
        // Test hovering over correlation cells
        const firstCell = correlationCells.first();
        await firstCell.hover();
        
        const tooltip = page.locator('[data-testid="correlation-tooltip"]');
        if (await tooltip.isVisible()) {
          const tooltipText = await tooltip.textContent();
          console.log(`📊 Correlation Tooltip: ${tooltipText}`);
        }
      }
      
      // 5. Test risk alerts
      await page.goto('/portfolio/risk-alerts');
      await page.waitForSelector('[data-testid="risk-alerts"]', { timeout: 15000 });
      
      // Create risk alert
      await page.click('[data-testid="create-risk-alert"]');
      await page.waitForSelector('[data-testid="alert-form"]', { timeout: 10000 });
      
      await page.selectOption('[data-testid="alert-type"]', 'drawdown');
      await page.fill('[data-testid="alert-threshold"]', '10');
      await page.selectOption('[data-testid="alert-frequency"]', 'daily');
      
      await page.click('[data-testid="save-risk-alert"]');
      await page.waitForSelector('[data-testid="alert-created"]', { timeout: 5000 });
      
      console.log('✅ Risk alert created successfully');
      
      // 6. Check existing alerts
      const activeAlerts = page.locator('[data-testid^="active-alert-"]');
      const alertCount = await activeAlerts.count();
      
      console.log(`🚨 Active Risk Alerts: ${alertCount}`);
      
      if (alertCount > 0) {
        const firstAlert = activeAlerts.first();
        const alertType = await firstAlert.locator('[data-testid="alert-type"]').textContent();
        const alertStatus = await firstAlert.locator('[data-testid="alert-status"]').textContent();
        
        console.log(`🚨 Alert: ${alertType} - ${alertStatus}`);
      }
      
      console.log('✅ Risk Analytics and Monitoring Integration passed');
    });

  });

  test.describe('Portfolio Rebalancing and Optimization @critical @enterprise @portfolio', () => {

    test('Automated Rebalancing Workflow Integration', async ({ page }) => {
      console.log('⚖️ Testing Automated Rebalancing Workflow Integration...');
      
      await authenticate(page);
      
      // 1. Navigate to rebalancing
      await page.goto('/portfolio/rebalancing');
      await page.waitForSelector('[data-testid="rebalancing-dashboard"]', { timeout: 15000 });
      
      // 2. Check current allocation
      const currentAllocations = page.locator('[data-testid^="current-allocation-"]');
      const allocationCount = await currentAllocations.count();
      
      console.log(`📊 Current Allocations: ${allocationCount} positions`);
      
      // 3. Set target allocations
      await page.click('[data-testid="set-target-allocations"]');
      await page.waitForSelector('[data-testid="target-allocation-form"]', { timeout: 10000 });
      
      const targetAllocations = [
        { sector: 'Technology', percentage: '40' },
        { sector: 'Healthcare', percentage: '25' },
        { sector: 'Financial', percentage: '20' },
        { sector: 'Consumer', percentage: '15' }
      ];
      
      for (const allocation of targetAllocations) {
        await page.fill(`[data-testid="target-${allocation.sector.toLowerCase()}"]`, allocation.percentage);
      }
      
      await page.click('[data-testid="save-target-allocations"]');
      await page.waitForSelector('[data-testid="targets-saved"]', { timeout: 5000 });
      
      console.log('✅ Target allocations set');
      
      // 4. Run rebalancing analysis
      await page.click('[data-testid="analyze-rebalancing"]');
      await page.waitForSelector('[data-testid="rebalancing-analysis"]', { timeout: 15000 });
      
      // Check rebalancing recommendations
      const recommendations = page.locator('[data-testid^="rebalancing-action-"]');
      const recommendationCount = await recommendations.count();
      
      console.log(`📋 Rebalancing Recommendations: ${recommendationCount} actions`);
      
      if (recommendationCount > 0) {
        for (let i = 0; i < Math.min(3, recommendationCount); i++) {
          const recommendation = recommendations.nth(i);
          const action = await recommendation.locator('[data-testid="action-type"]').textContent();
          const symbol = await recommendation.locator('[data-testid="action-symbol"]').textContent();
          const amount = await recommendation.locator('[data-testid="action-amount"]').textContent();
          
          console.log(`📋 ${action} ${amount} of ${symbol}`);
        }
      }
      
      // 5. Test dry run rebalancing
      await page.click('[data-testid="dry-run-rebalancing"]');
      await page.waitForSelector('[data-testid="dry-run-results"]', { timeout: 10000 });
      
      const beforeValue = await page.locator('[data-testid="before-rebalance-value"]').textContent();
      const afterValue = await page.locator('[data-testid="after-rebalance-value"]').textContent();
      const transactionCosts = await page.locator('[data-testid="transaction-costs"]').textContent();
      
      console.log(`💰 Rebalancing Preview:`);
      console.log(`  Before: ${beforeValue}`);
      console.log(`  After: ${afterValue}`);
      console.log(`  Costs: ${transactionCosts}`);
      
      // 6. Test rebalancing schedule
      await page.goto('/portfolio/rebalancing/schedule');
      await page.waitForSelector('[data-testid="rebalancing-schedule"]', { timeout: 15000 });
      
      await page.click('[data-testid="create-schedule"]');
      await page.waitForSelector('[data-testid="schedule-form"]', { timeout: 10000 });
      
      await page.selectOption('[data-testid="schedule-frequency"]', 'monthly');
      await page.selectOption('[data-testid="schedule-day"]', '1');
      await page.fill('[data-testid="rebalance-threshold"]', '5');
      await page.check('[data-testid="auto-execute"]');
      
      await page.click('[data-testid="save-schedule"]');
      await page.waitForSelector('[data-testid="schedule-created"]', { timeout: 5000 });
      
      console.log('✅ Automated rebalancing schedule created');
      
      console.log('✅ Automated Rebalancing Workflow Integration passed');
    });

    test('Portfolio Optimization Integration', async ({ page }) => {
      console.log('🎯 Testing Portfolio Optimization Integration...');
      
      await authenticate(page);
      
      // 1. Navigate to optimization
      await page.goto('/portfolio/optimization');
      await page.waitForSelector('[data-testid="optimization-dashboard"]', { timeout: 15000 });
      
      // 2. Set optimization parameters
      await page.click('[data-testid="configure-optimization"]');
      await page.waitForSelector('[data-testid="optimization-form"]', { timeout: 10000 });
      
      await page.selectOption('[data-testid="optimization-objective"]', 'max-sharpe');
      await page.fill('[data-testid="risk-tolerance"]', '15');
      await page.fill('[data-testid="min-allocation"]', '2');
      await page.fill('[data-testid="max-allocation"]', '25');
      
      // Add constraints
      await page.click('[data-testid="add-constraint"]');
      await page.selectOption('[data-testid="constraint-type"]', 'sector-limit');
      await page.selectOption('[data-testid="constraint-sector"]', 'technology');
      await page.fill('[data-testid="constraint-value"]', '40');
      
      await page.click('[data-testid="run-optimization"]');
      await page.waitForSelector('[data-testid="optimization-results"]', { timeout: 20000 });
      
      // 3. Review optimization results
      const optimizedReturn = await page.locator('[data-testid="optimized-return"]').textContent();
      const optimizedRisk = await page.locator('[data-testid="optimized-risk"]').textContent();
      const sharpeRatio = await page.locator('[data-testid="optimized-sharpe"]').textContent();
      
      console.log(`🎯 Optimization Results:`);
      console.log(`  Expected Return: ${optimizedReturn}`);
      console.log(`  Risk: ${optimizedRisk}`);
      console.log(`  Sharpe Ratio: ${sharpeRatio}`);
      
      // 4. Check efficient frontier
      const efficientFrontier = page.locator('[data-testid="efficient-frontier-chart"]');
      if (await efficientFrontier.isVisible()) {
        console.log('📊 Efficient frontier chart displayed');
        
        // Test frontier interaction
        await efficientFrontier.hover();
        const frontierTooltip = page.locator('[data-testid="frontier-tooltip"]');
        if (await frontierTooltip.isVisible()) {
          const tooltipText = await frontierTooltip.textContent();
          console.log(`📊 Frontier Point: ${tooltipText}`);
        }
      }
      
      // 5. Review allocation changes
      const allocationChanges = page.locator('[data-testid^="allocation-change-"]');
      const changeCount = await allocationChanges.count();
      
      console.log(`📋 Allocation Changes: ${changeCount} positions`);
      
      if (changeCount > 0) {
        for (let i = 0; i < Math.min(5, changeCount); i++) {
          const change = allocationChanges.nth(i);
          const symbol = await change.locator('[data-testid="change-symbol"]').textContent();
          const currentWeight = await change.locator('[data-testid="current-weight"]').textContent();
          const optimizedWeight = await change.locator('[data-testid="optimized-weight"]').textContent();
          
          console.log(`📊 ${symbol}: ${currentWeight} → ${optimizedWeight}`);
        }
      }
      
      // 6. Test optimization implementation
      await page.click('[data-testid="implement-optimization"]');
      await page.waitForSelector('[data-testid="implementation-preview"]', { timeout: 10000 });
      
      const implementationCost = await page.locator('[data-testid="implementation-cost"]').textContent();
      const tradeCount = await page.locator('[data-testid="trade-count"]').textContent();
      
      console.log(`💰 Implementation Cost: ${implementationCost}`);
      console.log(`📊 Required Trades: ${tradeCount}`);
      
      // Review before implementing
      await page.click('[data-testid="review-implementation"]');
      await page.waitForSelector('[data-testid="implementation-review"]', { timeout: 10000 });
      
      const reviewTrades = page.locator('[data-testid^="review-trade-"]');
      const reviewTradeCount = await reviewTrades.count();
      
      console.log(`📋 Implementation Review: ${reviewTradeCount} trades to execute`);
      
      console.log('✅ Portfolio Optimization Integration passed');
    });

  });

  test.afterEach(async () => {
    // Portfolio session summary
    console.log('\n📊 Portfolio Management Session Summary:');
    console.log(`Portfolios managed: ${portfolioSession.portfolios.length}`);
    console.log(`Holdings processed: ${portfolioSession.holdings.length}`);
    console.log(`Transactions recorded: ${portfolioSession.transactions.length}`);
    console.log(`Performance metrics: ${portfolioSession.performance.length}`);
    console.log(`Alerts configured: ${portfolioSession.alerts.length}`);
    console.log(`Errors encountered: ${portfolioSession.errors.length}`);
    
    // Log portfolio actions
    if (portfolioSession.portfolios.length > 0) {
      console.log('\n💼 Portfolio Actions:');
      portfolioSession.portfolios.forEach(portfolio => {
        console.log(`  ${portfolio.action} portfolio: ${portfolio.name} (ID: ${portfolio.id})`);
      });
    }
    
    // Log any errors
    if (portfolioSession.errors.length > 0) {
      console.log('\n❌ Portfolio Management Errors:');
      portfolioSession.errors.forEach(error => {
        console.log(`  ${error.timestamp}: ${error.message}`);
      });
    }
  });

});

export default {
  testConfig
};