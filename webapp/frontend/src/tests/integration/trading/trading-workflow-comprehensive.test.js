/**
 * Comprehensive Trading Workflow Integration Tests
 * Tests complete trading workflows from signal generation to execution
 * Integrated into existing enterprise testing framework
 */

import { test, expect } from '@playwright/test';

const testConfig = {
  baseURL: process.env.E2E_BASE_URL || 'https://d1zb7knau41vl9.cloudfront.net',
  apiURL: process.env.E2E_API_URL || 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev',
  testUser: {
    email: process.env.E2E_TEST_EMAIL || 'e2e-test@example.com',
    password: process.env.E2E_TEST_PASSWORD || 'E2ETest123!'
  },
  testSymbols: ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA'],
  timeout: 45000
};

test.describe('Comprehensive Trading Workflow Integration - Enterprise Framework', () => {
  
  let tradingSession = {
    signals: [],
    orders: [],
    executions: [],
    portfolioChanges: [],
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

  async function trackTradingAction(action, data) {
    tradingSession[action].push({
      ...data,
      timestamp: new Date().toISOString()
    });
  }

  test.beforeEach(async ({ page }) => {
    // Reset trading session tracking
    tradingSession = { signals: [], orders: [], executions: [], portfolioChanges: [], errors: [] };
    
    // Setup trading-specific monitoring
    page.on('console', msg => {
      if (msg.type() === 'error' && msg.text().includes('trading')) {
        tradingSession.errors.push({
          message: msg.text(),
          timestamp: new Date().toISOString()
        });
      }
    });

    await page.goto(testConfig.baseURL);
    await page.waitForLoadState('networkidle');
  });

  test.describe('Signal Generation to Order Workflow @critical @enterprise @trading', () => {

    test('Complete Signal Analysis to Order Placement Flow', async ({ page }) => {
      console.log('🎯 Testing Complete Signal Analysis to Order Placement Flow...');
      
      await authenticate(page);
      
      // 1. Navigate to trading signals
      await page.goto('/trading/signals');
      await page.waitForSelector('[data-testid="trading-signals-page"]', { timeout: 20000 });
      
      // 2. Analyze available signals
      const signalCards = page.locator('[data-testid^="signal-card-"]');
      const signalCount = await signalCards.count();
      
      if (signalCount > 0) {
        console.log(`📊 Found ${signalCount} trading signals`);
        
        // 3. Select and analyze first signal
        const firstSignal = signalCards.first();
        const signalSymbol = await firstSignal.locator('[data-testid="signal-symbol"]').textContent();
        const signalType = await firstSignal.locator('[data-testid="signal-type"]').textContent();
        const signalStrength = await firstSignal.locator('[data-testid="signal-strength"]').textContent();
        
        await trackTradingAction('signals', {
          symbol: signalSymbol,
          type: signalType,
          strength: signalStrength
        });
        
        // 4. Click signal for detailed analysis
        await firstSignal.click();
        await page.waitForSelector('[data-testid="signal-detail-modal"]', { timeout: 10000 });
        
        // 5. Analyze signal details
        const detailElements = {
          indicators: '[data-testid="signal-indicators"]',
          confidence: '[data-testid="signal-confidence"]',
          riskLevel: '[data-testid="signal-risk-level"]',
          targetPrice: '[data-testid="signal-target-price"]'
        };
        
        for (const [key, selector] of Object.entries(detailElements)) {
          const element = page.locator(selector);
          if (await element.isVisible()) {
            const value = await element.textContent();
            console.log(`📋 Signal ${key}: ${value}`);
          }
        }
        
        // 6. Navigate to stock analysis
        await page.click('[data-testid="analyze-stock-button"]');
        await page.waitForURL(`**/stocks/${signalSymbol}**`);
        
        // 7. Perform technical analysis
        await page.click('[data-testid="technical-analysis-tab"]');
        await page.waitForSelector('[data-testid="technical-analysis"]', { timeout: 15000 });
        
        // 8. Check multiple technical indicators
        const indicators = ['RSI', 'MACD', 'SMA-20', 'SMA-50', 'Bollinger'];
        for (const indicator of indicators) {
          const indicatorElement = page.locator(`[data-testid="indicator-${indicator}"]`);
          if (await indicatorElement.isVisible()) {
            const value = await indicatorElement.locator('[data-testid="indicator-value"]').textContent();
            const signal = await indicatorElement.locator('[data-testid="indicator-signal"]').textContent();
            console.log(`📈 ${indicator}: ${value} (${signal})`);
          }
        }
        
        // 9. Navigate to order placement
        await page.click('[data-testid="place-order-button"]');
        await page.waitForSelector('[data-testid="order-form"]', { timeout: 10000 });
        
        // 10. Fill order form
        await page.selectOption('[data-testid="order-type"]', 'limit');
        await page.fill('[data-testid="quantity-input"]', '10');
        await page.fill('[data-testid="price-input"]', '100.00');
        await page.selectOption('[data-testid="time-in-force"]', 'day');
        
        // 11. Review order details
        await page.click('[data-testid="review-order-button"]');
        await page.waitForSelector('[data-testid="order-review-modal"]', { timeout: 5000 });
        
        // 12. Verify order details
        const orderSymbol = await page.locator('[data-testid="review-symbol"]').textContent();
        const orderQuantity = await page.locator('[data-testid="review-quantity"]').textContent();
        const orderPrice = await page.locator('[data-testid="review-price"]').textContent();
        
        expect(orderSymbol).toContain(signalSymbol);
        expect(orderQuantity).toContain('10');
        expect(orderPrice).toContain('100.00');
        
        await trackTradingAction('orders', {
          symbol: orderSymbol,
          quantity: orderQuantity,
          price: orderPrice,
          type: 'limit'
        });
        
        // 13. Submit order (in test mode)
        await page.click('[data-testid="submit-order-button"]');
        
        // 14. Verify order confirmation
        await page.waitForSelector('[data-testid="order-confirmation"]', { timeout: 10000 });
        const orderConfirmation = await page.locator('[data-testid="order-confirmation"]').textContent();
        expect(orderConfirmation).toContain('Order submitted successfully');
        
        console.log('✅ Complete Signal Analysis to Order Placement Flow passed');
      } else {
        console.log('⚠️ No trading signals available for testing');
      }
    });

    test('Signal Filtering and Advanced Analysis Workflow', async ({ page }) => {
      console.log('🔍 Testing Signal Filtering and Advanced Analysis Workflow...');
      
      await authenticate(page);
      await page.goto('/trading/signals');
      
      // 1. Test signal filtering capabilities
      const filters = {
        signalType: ['BUY', 'SELL', 'HOLD'],
        strength: ['HIGH', 'MEDIUM', 'LOW'],
        sector: ['Technology', 'Healthcare', 'Financial'],
        timeframe: ['1D', '1W', '1M']
      };
      
      for (const [filterType, options] of Object.entries(filters)) {
        const filterSelect = page.locator(`[data-testid="${filterType}-filter"]`);
        if (await filterSelect.isVisible()) {
          for (const option of options.slice(0, 2)) {
            await filterSelect.selectOption(option);
            await page.waitForTimeout(2000);
            
            // Verify filter results
            const filteredSignals = await page.locator('[data-testid^="signal-card-"]').count();
            console.log(`📊 ${filterType} filter (${option}): ${filteredSignals} signals`);
          }
          
          // Reset filter
          await filterSelect.selectOption('ALL');
          await page.waitForTimeout(1000);
        }
      }
      
      // 2. Test signal sorting
      const sortOptions = ['strength', 'symbol', 'timestamp', 'performance'];
      for (const sortOption of sortOptions) {
        const sortButton = page.locator(`[data-testid="sort-${sortOption}"]`);
        if (await sortButton.isVisible()) {
          await sortButton.click();
          await page.waitForTimeout(1000);
          
          // Verify sorting applied
          const firstSignal = await page.locator('[data-testid^="signal-card-"]').first().textContent();
          console.log(`🔄 Sorted by ${sortOption}: First signal - ${firstSignal.substring(0, 50)}...`);
        }
      }
      
      // 3. Test bulk signal analysis
      const signalCheckboxes = page.locator('[data-testid^="signal-checkbox-"]');
      const checkboxCount = await signalCheckboxes.count();
      
      if (checkboxCount > 0) {
        // Select multiple signals
        for (let i = 0; i < Math.min(3, checkboxCount); i++) {
          await signalCheckboxes.nth(i).click();
        }
        
        // Perform bulk analysis
        await page.click('[data-testid="bulk-analyze-button"]');
        await page.waitForSelector('[data-testid="bulk-analysis-modal"]', { timeout: 10000 });
        
        // Verify bulk analysis results
        const analysisResults = page.locator('[data-testid^="bulk-result-"]');
        const resultCount = await analysisResults.count();
        expect(resultCount).toBeGreaterThan(0);
        
        console.log(`📊 Bulk analysis completed for ${resultCount} signals`);
        
        await page.click('[data-testid="close-bulk-analysis"]');
      }
      
      console.log('✅ Signal Filtering and Advanced Analysis Workflow passed');
    });

  });

  test.describe('Portfolio Integration with Trading @critical @enterprise @trading', () => {

    test('Portfolio Impact Analysis for Trading Decisions', async ({ page }) => {
      console.log('💼 Testing Portfolio Impact Analysis for Trading Decisions...');
      
      await authenticate(page);
      
      // 1. Get current portfolio state
      await page.goto('/portfolio');
      await page.waitForSelector('[data-testid="portfolio-summary"]', { timeout: 15000 });
      
      const initialPortfolioValue = await page.locator('[data-testid="portfolio-total-value"]').textContent();
      const initialCashBalance = await page.locator('[data-testid="cash-balance"]').textContent();
      
      console.log(`💰 Initial Portfolio Value: ${initialPortfolioValue}`);
      console.log(`💵 Initial Cash Balance: ${initialCashBalance}`);
      
      await trackTradingAction('portfolioChanges', {
        type: 'initial_state',
        portfolioValue: initialPortfolioValue,
        cashBalance: initialCashBalance
      });
      
      // 2. Navigate to trading with portfolio context
      await page.goto('/trading');
      await page.waitForSelector('[data-testid="trading-page"]', { timeout: 15000 });
      
      // 3. Verify portfolio information is displayed in trading context
      const tradingPortfolioValue = await page.locator('[data-testid="trading-portfolio-value"]').textContent();
      const tradingBuyingPower = await page.locator('[data-testid="buying-power"]').textContent();
      
      console.log(`💼 Portfolio Value in Trading: ${tradingPortfolioValue}`);
      console.log(`⚡ Buying Power: ${tradingBuyingPower}`);
      
      // 4. Test position size calculator
      const testSymbol = testConfig.testSymbols[0];
      await page.goto(`/trading/calculator?symbol=${testSymbol}`);
      await page.waitForSelector('[data-testid="position-calculator"]', { timeout: 15000 });
      
      // 5. Calculate position size based on portfolio
      await page.fill('[data-testid="risk-percentage"]', '2');
      await page.fill('[data-testid="stop-loss-percentage"]', '5');
      await page.click('[data-testid="calculate-position"]');
      
      await page.waitForSelector('[data-testid="calculated-position"]', { timeout: 5000 });
      const recommendedShares = await page.locator('[data-testid="recommended-shares"]').textContent();
      const maxRisk = await page.locator('[data-testid="max-risk-amount"]').textContent();
      
      console.log(`📊 Recommended Shares: ${recommendedShares}`);
      console.log(`⚠️ Max Risk Amount: ${maxRisk}`);
      
      // 6. Test order impact on portfolio
      await page.goto(`/stocks/${testSymbol}`);
      await page.click('[data-testid="trade-button"]');
      await page.waitForSelector('[data-testid="order-form"]', { timeout: 10000 });
      
      // 7. Fill order and check portfolio impact preview
      await page.fill('[data-testid="quantity-input"]', recommendedShares.replace(/[^\d]/g, ''));
      await page.waitForTimeout(1000);
      
      // Verify portfolio impact is shown
      const portfolioImpact = page.locator('[data-testid="portfolio-impact"]');
      if (await portfolioImpact.isVisible()) {
        const newPortfolioValue = await portfolioImpact.locator('[data-testid="new-portfolio-value"]').textContent();
        const newCashBalance = await portfolioImpact.locator('[data-testid="new-cash-balance"]').textContent();
        
        console.log(`📈 Projected Portfolio Value: ${newPortfolioValue}`);
        console.log(`💰 Projected Cash Balance: ${newCashBalance}`);
        
        await trackTradingAction('portfolioChanges', {
          type: 'projected_impact',
          newPortfolioValue,
          newCashBalance,
          symbol: testSymbol
        });
      }
      
      console.log('✅ Portfolio Impact Analysis for Trading Decisions passed');
    });

    test('Risk Management Integration Workflow', async ({ page }) => {
      console.log('⚠️ Testing Risk Management Integration Workflow...');
      
      await authenticate(page);
      
      // 1. Navigate to risk management dashboard
      await page.goto('/trading/risk-management');
      await page.waitForSelector('[data-testid="risk-dashboard"]', { timeout: 15000 });
      
      // 2. Check current risk metrics
      const riskMetrics = {
        portfolioRisk: '[data-testid="portfolio-risk-score"]',
        valueAtRisk: '[data-testid="value-at-risk"]',
        maxDrawdown: '[data-testid="max-drawdown"]',
        sharpeRatio: '[data-testid="sharpe-ratio"]',
        beta: '[data-testid="portfolio-beta"]'
      };
      
      for (const [metric, selector] of Object.entries(riskMetrics)) {
        const element = page.locator(selector);
        if (await element.isVisible()) {
          const value = await element.textContent();
          console.log(`📊 ${metric}: ${value}`);
        }
      }
      
      // 3. Test risk alerts and limits
      const riskAlerts = page.locator('[data-testid^="risk-alert-"]');
      const alertCount = await riskAlerts.count();
      
      if (alertCount > 0) {
        console.log(`⚠️ Found ${alertCount} risk alerts`);
        
        for (let i = 0; i < alertCount; i++) {
          const alert = riskAlerts.nth(i);
          const alertType = await alert.locator('[data-testid="alert-type"]').textContent();
          const alertMessage = await alert.locator('[data-testid="alert-message"]').textContent();
          
          console.log(`🚨 Risk Alert ${i + 1}: ${alertType} - ${alertMessage}`);
        }
      }
      
      // 4. Test setting risk limits
      await page.click('[data-testid="set-risk-limits"]');
      await page.waitForSelector('[data-testid="risk-limits-modal"]', { timeout: 10000 });
      
      // Configure risk limits
      await page.fill('[data-testid="max-position-size"]', '5');
      await page.fill('[data-testid="max-daily-loss"]', '2');
      await page.fill('[data-testid="max-portfolio-risk"]', '15');
      
      await page.click('[data-testid="save-risk-limits"]');
      await page.waitForSelector('[data-testid="limits-saved-confirmation"]', { timeout: 5000 });
      
      // 5. Test risk limits enforcement
      const testSymbol = testConfig.testSymbols[1];
      await page.goto(`/stocks/${testSymbol}`);
      await page.click('[data-testid="trade-button"]');
      
      // Try to place order that exceeds risk limits
      await page.fill('[data-testid="quantity-input"]', '1000');
      await page.waitForTimeout(1000);
      
      // Should show risk warning
      const riskWarning = page.locator('[data-testid="risk-limit-warning"]');
      if (await riskWarning.isVisible()) {
        const warningMessage = await riskWarning.textContent();
        console.log(`⚠️ Risk limit warning: ${warningMessage}`);
        
        // Verify order is blocked or requires confirmation
        const proceedButton = page.locator('[data-testid="risk-override-confirm"]');
        const blockMessage = page.locator('[data-testid="order-blocked"]');
        
        if (await proceedButton.isVisible()) {
          console.log('✅ Risk override confirmation required');
        } else if (await blockMessage.isVisible()) {
          console.log('✅ Order properly blocked by risk limits');
        }
      }
      
      console.log('✅ Risk Management Integration Workflow passed');
    });

  });

  test.describe('Order Management and Execution @critical @enterprise @trading', () => {

    test('Complete Order Lifecycle Integration', async ({ page }) => {
      console.log('🔄 Testing Complete Order Lifecycle Integration...');
      
      await authenticate(page);
      
      // 1. Navigate to order management
      await page.goto('/trading/orders');
      await page.waitForSelector('[data-testid="order-management"]', { timeout: 15000 });
      
      // 2. Check active orders
      const activeOrders = page.locator('[data-testid^="active-order-"]');
      const activeOrderCount = await activeOrders.count();
      
      console.log(`📋 Active Orders: ${activeOrderCount}`);
      
      // 3. Create new order for testing
      await page.click('[data-testid="create-new-order"]');
      await page.waitForSelector('[data-testid="order-form"]', { timeout: 10000 });
      
      const testSymbol = testConfig.testSymbols[2];
      
      // 4. Fill order details
      await page.fill('[data-testid="symbol-input"]', testSymbol);
      await page.selectOption('[data-testid="order-side"]', 'buy');
      await page.selectOption('[data-testid="order-type"]', 'limit');
      await page.fill('[data-testid="quantity-input"]', '5');
      await page.fill('[data-testid="price-input"]', '50.00');
      await page.selectOption('[data-testid="time-in-force"]', 'day');
      
      // 5. Add order conditions
      await page.click('[data-testid="add-conditions"]');
      await page.selectOption('[data-testid="condition-type"]', 'stop-loss');
      await page.fill('[data-testid="stop-price"]', '45.00');
      
      // 6. Submit order
      await page.click('[data-testid="submit-order"]');
      await page.waitForSelector('[data-testid="order-submitted"]', { timeout: 10000 });
      
      const orderId = await page.locator('[data-testid="order-id"]').textContent();
      console.log(`📝 Order submitted with ID: ${orderId}`);
      
      await trackTradingAction('orders', {
        orderId,
        symbol: testSymbol,
        side: 'buy',
        type: 'limit',
        quantity: '5',
        price: '50.00'
      });
      
      // 7. Monitor order status
      await page.goto('/trading/orders');
      await page.waitForSelector(`[data-testid="order-${orderId}"]`, { timeout: 15000 });
      
      const orderRow = page.locator(`[data-testid="order-${orderId}"]`);
      const orderStatus = await orderRow.locator('[data-testid="order-status"]').textContent();
      
      console.log(`📊 Order Status: ${orderStatus}`);
      
      // 8. Test order modification
      if (orderStatus.includes('PENDING') || orderStatus.includes('OPEN')) {
        await orderRow.locator('[data-testid="modify-order"]').click();
        await page.waitForSelector('[data-testid="modify-order-modal"]', { timeout: 10000 });
        
        // Modify price
        await page.fill('[data-testid="new-price"]', '52.00');
        await page.click('[data-testid="confirm-modification"]');
        
        await page.waitForSelector('[data-testid="order-modified"]', { timeout: 5000 });
        console.log('✅ Order modification successful');
      }
      
      // 9. Test order cancellation
      await page.goto('/trading/orders');
      await page.waitForSelector(`[data-testid="order-${orderId}"]`, { timeout: 10000 });
      
      const cancelButton = page.locator(`[data-testid="cancel-order-${orderId}"]`);
      if (await cancelButton.isVisible()) {
        await cancelButton.click();
        await page.waitForSelector('[data-testid="cancel-confirmation"]', { timeout: 5000 });
        await page.click('[data-testid="confirm-cancel"]');
        
        await page.waitForSelector('[data-testid="order-cancelled"]', { timeout: 5000 });
        console.log('✅ Order cancellation successful');
      }
      
      // 10. Check order history
      await page.goto('/trading/orders/history');
      await page.waitForSelector('[data-testid="order-history"]', { timeout: 15000 });
      
      const historyRows = page.locator('[data-testid^="history-order-"]');
      const historyCount = await historyRows.count();
      
      console.log(`📚 Order History: ${historyCount} orders`);
      
      console.log('✅ Complete Order Lifecycle Integration passed');
    });

    test('Advanced Order Types Integration', async ({ page }) => {
      console.log('⚙️ Testing Advanced Order Types Integration...');
      
      await authenticate(page);
      await page.goto('/trading/advanced-orders');
      
      // 1. Test bracket order creation
      await page.click('[data-testid="create-bracket-order"]');
      await page.waitForSelector('[data-testid="bracket-order-form"]', { timeout: 10000 });
      
      const testSymbol = testConfig.testSymbols[3];
      
      // Configure bracket order
      await page.fill('[data-testid="symbol-input"]', testSymbol);
      await page.fill('[data-testid="entry-quantity"]', '10');
      await page.fill('[data-testid="entry-price"]', '100.00');
      await page.fill('[data-testid="take-profit-price"]', '110.00');
      await page.fill('[data-testid="stop-loss-price"]', '95.00');
      
      await page.click('[data-testid="submit-bracket-order"]');
      await page.waitForSelector('[data-testid="bracket-order-created"]', { timeout: 10000 });
      
      console.log('✅ Bracket order created successfully');
      
      // 2. Test OCO (One-Cancels-Other) order
      await page.click('[data-testid="create-oco-order"]');
      await page.waitForSelector('[data-testid="oco-order-form"]', { timeout: 10000 });
      
      // Configure OCO order
      await page.fill('[data-testid="oco-symbol"]', testSymbol);
      await page.fill('[data-testid="oco-quantity"]', '15');
      await page.fill('[data-testid="limit-price"]', '105.00');
      await page.fill('[data-testid="stop-price"]', '98.00');
      
      await page.click('[data-testid="submit-oco-order"]');
      await page.waitForSelector('[data-testid="oco-order-created"]', { timeout: 10000 });
      
      console.log('✅ OCO order created successfully');
      
      // 3. Test trailing stop order
      await page.click('[data-testid="create-trailing-stop"]');
      await page.waitForSelector('[data-testid="trailing-stop-form"]', { timeout: 10000 });
      
      // Configure trailing stop
      await page.fill('[data-testid="trailing-symbol"]', testSymbol);
      await page.fill('[data-testid="trailing-quantity"]', '20');
      await page.selectOption('[data-testid="trail-type"]', 'percentage');
      await page.fill('[data-testid="trail-amount"]', '5');
      
      await page.click('[data-testid="submit-trailing-stop"]');
      await page.waitForSelector('[data-testid="trailing-stop-created"]', { timeout: 10000 });
      
      console.log('✅ Trailing stop order created successfully');
      
      // 4. Test conditional orders
      await page.click('[data-testid="create-conditional-order"]');
      await page.waitForSelector('[data-testid="conditional-order-form"]', { timeout: 10000 });
      
      // Configure conditional order
      await page.fill('[data-testid="conditional-symbol"]', testSymbol);
      await page.selectOption('[data-testid="condition-operator"]', 'above');
      await page.fill('[data-testid="condition-price"]', '102.00');
      await page.fill('[data-testid="order-quantity"]', '8');
      await page.fill('[data-testid="order-price"]', '103.00');
      
      await page.click('[data-testid="submit-conditional-order"]');
      await page.waitForSelector('[data-testid="conditional-order-created"]', { timeout: 10000 });
      
      console.log('✅ Conditional order created successfully');
      
      console.log('✅ Advanced Order Types Integration passed');
    });

  });

  test.afterEach(async () => {
    // Trading session summary
    console.log('\n📊 Trading Session Summary:');
    console.log(`Signals analyzed: ${tradingSession.signals.length}`);
    console.log(`Orders placed: ${tradingSession.orders.length}`);
    console.log(`Portfolio changes: ${tradingSession.portfolioChanges.length}`);
    console.log(`Errors encountered: ${tradingSession.errors.length}`);
    
    if (tradingSession.errors.length > 0) {
      console.log('\n❌ Trading Errors:');
      tradingSession.errors.forEach(error => {
        console.log(`  ${error.timestamp}: ${error.message}`);
      });
    }
  });

});

export default {
  testConfig
};