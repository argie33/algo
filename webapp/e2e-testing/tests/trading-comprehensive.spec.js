/**
 * Comprehensive E2E Trading Workflow Tests
 * Tests paper trading with real broker APIs, order management, and portfolio integration
 * No mocks - validates real trading infrastructure and risk management
 */

import { test, expect } from '@playwright/test';

test.describe('Trading Workflow Integration Tests', () => {
  let page;
  let context;
  
  test.beforeEach(async ({ browser }) => {
    context = await browser.newContext({
      // Enable debugging and performance monitoring
      recordVideo: { dir: 'test-results/videos/' },
      recordHar: { path: 'test-results/network.har' }
    });
    page = await context.newPage();
    
    // Enable console logging for debugging
    page.on('console', msg => console.log(`Page log: ${msg.text()}`));
    page.on('pageerror', err => console.error(`Page error: ${err.message}`));
  });

  test.afterEach(async () => {
    await context.close();
  });

  test('should complete full paper trading workflow', async () => {
    console.log('🔄 Testing complete paper trading workflow...');
    
    // Navigate to trading page
    await page.goto('/protected-portfolio');
    
    // Wait for authentication to complete
    await page.waitForSelector('[data-testid="portfolio-container"]', { timeout: 30000 });
    
    // Verify paper trading mode is enabled
    const paperTradingBadge = await page.locator('[data-testid="paper-trading-badge"]');
    await expect(paperTradingBadge).toBeVisible();
    await expect(paperTradingBadge).toContainText('Paper Trading');
    
    // Test buy order creation
    await page.click('[data-testid="new-order-button"]');
    await page.waitForSelector('[data-testid="order-form"]');
    
    // Fill order form with valid stock symbol
    await page.fill('[data-testid="symbol-input"]', 'AAPL');
    await page.selectOption('[data-testid="order-type"]', 'buy');
    await page.fill('[data-testid="quantity-input"]', '10');
    await page.selectOption('[data-testid="order-duration"]', 'day');
    
    // Verify order preview shows correct calculations
    await page.click('[data-testid="preview-order"]');
    await page.waitForSelector('[data-testid="order-preview"]');
    
    const estimatedCost = await page.locator('[data-testid="estimated-cost"]');
    await expect(estimatedCost).toBeVisible();
    
    // Validate cost calculation includes commission
    const costText = await estimatedCost.textContent();
    expect(costText).toMatch(/\$[\d,]+\.\d{2}/);
    
    // Submit paper trading order
    await page.click('[data-testid="submit-order"]');
    
    // Verify order confirmation
    await page.waitForSelector('[data-testid="order-confirmation"]', { timeout: 10000 });
    const confirmationMessage = await page.locator('[data-testid="confirmation-message"]');
    await expect(confirmationMessage).toContainText('Order placed successfully');
    
    // Check order appears in active orders
    await page.click('[data-testid="active-orders-tab"]');
    await page.waitForSelector('[data-testid="order-list"]');
    
    const orderRow = await page.locator('[data-testid="order-row"]').first();
    await expect(orderRow).toBeVisible();
    await expect(orderRow).toContainText('AAPL');
    await expect(orderRow).toContainText('BUY');
    await expect(orderRow).toContainText('10');
  });

  test('should handle order validation and error cases', async () => {
    console.log('🔄 Testing order validation and error handling...');
    
    await page.goto('/protected-portfolio');
    await page.waitForSelector('[data-testid="portfolio-container"]', { timeout: 30000 });
    
    // Test invalid symbol validation
    await page.click('[data-testid="new-order-button"]');
    await page.fill('[data-testid="symbol-input"]', 'INVALID');
    await page.fill('[data-testid="quantity-input"]', '10');
    
    await page.click('[data-testid="preview-order"]');
    
    // Should show error for invalid symbol
    await page.waitForSelector('[data-testid="error-message"]', { timeout: 5000 });
    const errorMessage = await page.locator('[data-testid="error-message"]');
    await expect(errorMessage).toContainText('Invalid symbol');
    
    // Test insufficient funds validation
    await page.fill('[data-testid="symbol-input"]', 'AAPL');
    await page.fill('[data-testid="quantity-input"]', '999999');
    
    await page.click('[data-testid="preview-order"]');
    await page.waitForSelector('[data-testid="error-message"]');
    
    const fundsError = await page.locator('[data-testid="error-message"]');
    await expect(fundsError).toContainText('Insufficient funds');
    
    // Test market hours validation (if applicable)
    const currentTime = new Date();
    const isAfterHours = currentTime.getHours() >= 16 || currentTime.getHours() < 9;
    
    if (isAfterHours) {
      await page.fill('[data-testid="quantity-input"]', '1');
      await page.selectOption('[data-testid="order-type"]', 'market');
      
      await page.click('[data-testid="preview-order"]');
      
      // Should warn about market hours for market orders
      const warningMessage = await page.locator('[data-testid="warning-message"]');
      await expect(warningMessage).toContainText('market hours');
    }
  });

  test('should integrate with real-time market data for pricing', async () => {
    console.log('🔄 Testing real-time market data integration...');
    
    await page.goto('/protected-portfolio');
    await page.waitForSelector('[data-testid="portfolio-container"]', { timeout: 30000 });
    
    await page.click('[data-testid="new-order-button"]');
    await page.fill('[data-testid="symbol-input"]', 'MSFT');
    
    // Wait for real-time price to load
    await page.waitForSelector('[data-testid="current-price"]', { timeout: 10000 });
    const currentPrice = await page.locator('[data-testid="current-price"]');
    await expect(currentPrice).toBeVisible();
    
    // Verify price format
    const priceText = await currentPrice.textContent();
    expect(priceText).toMatch(/\$\d+\.\d{2}/);
    
    // Test price updates (if real-time is working)
    const initialPrice = priceText;
    await page.waitForTimeout(5000);
    
    // Price might update - check if element is still valid
    const updatedPrice = await currentPrice.textContent();
    expect(updatedPrice).toMatch(/\$\d+\.\d{2}/);
    
    // Verify bid/ask spread if available
    const bidPrice = await page.locator('[data-testid="bid-price"]');
    const askPrice = await page.locator('[data-testid="ask-price"]');
    
    if (await bidPrice.isVisible() && await askPrice.isVisible()) {
      const bidText = await bidPrice.textContent();
      const askText = await askPrice.textContent();
      
      expect(bidText).toMatch(/\$\d+\.\d{2}/);
      expect(askText).toMatch(/\$\d+\.\d{2}/);
      
      // Ask should be higher than bid
      const bidValue = parseFloat(bidText.replace('$', ''));
      const askValue = parseFloat(askText.replace('$', ''));
      expect(askValue).toBeGreaterThan(bidValue);
    }
  });

  test('should handle portfolio position updates after trades', async () => {
    console.log('🔄 Testing portfolio position updates...');
    
    await page.goto('/protected-portfolio');
    await page.waitForSelector('[data-testid="portfolio-container"]', { timeout: 30000 });
    
    // Record initial portfolio value
    const initialValue = await page.locator('[data-testid="portfolio-value"]');
    const initialValueText = await initialValue.textContent();
    
    // Place a small buy order
    await page.click('[data-testid="new-order-button"]');
    await page.fill('[data-testid="symbol-input"]', 'TSLA');
    await page.fill('[data-testid="quantity-input"]', '1');
    await page.selectOption('[data-testid="order-type"]', 'market');
    
    await page.click('[data-testid="preview-order"]');
    await page.waitForSelector('[data-testid="order-preview"]');
    await page.click('[data-testid="submit-order"]');
    
    // Wait for order confirmation
    await page.waitForSelector('[data-testid="order-confirmation"]', { timeout: 10000 });
    
    // Check if position appears in holdings (for paper trading, this might be immediate)
    await page.click('[data-testid="holdings-tab"]');
    await page.waitForSelector('[data-testid="holdings-list"]');
    
    // Look for TSLA position
    const tslaPosition = page.locator('[data-testid="position-row"]').filter({ hasText: 'TSLA' });
    
    if (await tslaPosition.isVisible()) {
      await expect(tslaPosition).toContainText('1'); // quantity
      
      // Verify position value is calculated
      const positionValue = await tslaPosition.locator('[data-testid="position-value"]');
      await expect(positionValue).toBeVisible();
      
      const valueText = await positionValue.textContent();
      expect(valueText).toMatch(/\$\d+\.\d{2}/);
    }
    
    // Verify portfolio summary updated
    await page.click('[data-testid="summary-tab"]');
    const updatedValue = await page.locator('[data-testid="portfolio-value"]');
    const updatedValueText = await updatedValue.textContent();
    
    // Portfolio value should have changed (decreased by trade cost in paper trading)
    expect(updatedValueText).not.toBe(initialValueText);
  });

  test('should support limit orders with price monitoring', async () => {
    console.log('🔄 Testing limit order functionality...');
    
    await page.goto('/protected-portfolio');
    await page.waitForSelector('[data-testid="portfolio-container"]', { timeout: 30000 });
    
    await page.click('[data-testid="new-order-button"]');
    await page.fill('[data-testid="symbol-input"]', 'NVDA');
    await page.selectOption('[data-testid="order-type"]', 'limit');
    
    // Limit order should show price input
    await page.waitForSelector('[data-testid="limit-price-input"]');
    
    await page.fill('[data-testid="quantity-input"]', '5');
    await page.fill('[data-testid="limit-price-input"]', '800.00');
    await page.selectOption('[data-testid="order-duration"]', 'gtc'); // Good Till Canceled
    
    // Preview limit order
    await page.click('[data-testid="preview-order"]');
    await page.waitForSelector('[data-testid="order-preview"]');
    
    // Verify limit order details
    const orderSummary = await page.locator('[data-testid="order-summary"]');
    await expect(orderSummary).toContainText('NVDA');
    await expect(orderSummary).toContainText('LIMIT');
    await expect(orderSummary).toContainText('$800.00');
    await expect(orderSummary).toContainText('GTC');
    
    // Submit limit order
    await page.click('[data-testid="submit-order"]');
    await page.waitForSelector('[data-testid="order-confirmation"]');
    
    // Verify order is in pending orders
    await page.click('[data-testid="pending-orders-tab"]');
    await page.waitForSelector('[data-testid="pending-orders-list"]');
    
    const limitOrder = page.locator('[data-testid="pending-order"]').filter({ hasText: 'NVDA' });
    await expect(limitOrder).toBeVisible();
    await expect(limitOrder).toContainText('LIMIT');
    await expect(limitOrder).toContainText('$800.00');
    
    // Test order cancellation
    const cancelButton = limitOrder.locator('[data-testid="cancel-order"]');
    await cancelButton.click();
    
    // Confirm cancellation
    await page.waitForSelector('[data-testid="cancel-confirmation"]');
    await page.click('[data-testid="confirm-cancel"]');
    
    // Verify order removed from pending list
    await page.waitForTimeout(2000);
    await expect(limitOrder).not.toBeVisible();
  });

  test('should handle stop-loss orders and risk management', async () => {
    console.log('🔄 Testing stop-loss orders and risk management...');
    
    await page.goto('/protected-portfolio');
    await page.waitForSelector('[data-testid="portfolio-container"]', { timeout: 30000 });
    
    // First, create a position to set stop-loss on
    await page.click('[data-testid="new-order-button"]');
    await page.fill('[data-testid="symbol-input"]', 'AMD');
    await page.fill('[data-testid="quantity-input"]', '10');
    await page.selectOption('[data-testid="order-type"]', 'market');
    
    await page.click('[data-testid="preview-order"]');
    await page.click('[data-testid="submit-order"]');
    await page.waitForSelector('[data-testid="order-confirmation"]');
    
    // Now create stop-loss order
    await page.click('[data-testid="new-order-button"]');
    await page.fill('[data-testid="symbol-input"]', 'AMD');
    await page.selectOption('[data-testid="order-type"]', 'stop-loss');
    
    // Stop-loss should show stop price input
    await page.waitForSelector('[data-testid="stop-price-input"]');
    
    await page.fill('[data-testid="quantity-input"]', '10');
    await page.fill('[data-testid="stop-price-input"]', '140.00');
    
    // Preview stop-loss order
    await page.click('[data-testid="preview-order"]');
    await page.waitForSelector('[data-testid="order-preview"]');
    
    // Verify stop-loss details
    const stopOrderSummary = await page.locator('[data-testid="order-summary"]');
    await expect(stopOrderSummary).toContainText('AMD');
    await expect(stopOrderSummary).toContainText('STOP-LOSS');
    await expect(stopOrderSummary).toContainText('$140.00');
    
    // Test risk warning if stop price is too low
    const riskWarning = await page.locator('[data-testid="risk-warning"]');
    if (await riskWarning.isVisible()) {
      await expect(riskWarning).toContainText('significant loss');
    }
    
    await page.click('[data-testid="submit-order"]');
    await page.waitForSelector('[data-testid="order-confirmation"]');
    
    // Verify stop-loss appears in risk management section
    await page.click('[data-testid="risk-management-tab"]');
    await page.waitForSelector('[data-testid="stop-orders-list"]');
    
    const stopOrder = page.locator('[data-testid="stop-order"]').filter({ hasText: 'AMD' });
    await expect(stopOrder).toBeVisible();
    await expect(stopOrder).toContainText('$140.00');
  });

  test('should validate day trading restrictions and buying power', async () => {
    console.log('🔄 Testing day trading restrictions and buying power...');
    
    await page.goto('/protected-portfolio');
    await page.waitForSelector('[data-testid="portfolio-container"]', { timeout: 30000 });
    
    // Check buying power display
    const buyingPower = await page.locator('[data-testid="buying-power"]');
    await expect(buyingPower).toBeVisible();
    
    const buyingPowerText = await buyingPower.textContent();
    expect(buyingPowerText).toMatch(/\$[\d,]+\.\d{2}/);
    
    // Test day trading pattern detection
    await page.click('[data-testid="new-order-button"]');
    await page.fill('[data-testid="symbol-input"]', 'SPY');
    await page.fill('[data-testid="quantity-input"]', '100');
    
    // Buy order
    await page.selectOption('[data-testid="order-type"]', 'market');
    await page.click('[data-testid="preview-order"]');
    
    // Check for day trading warnings
    const dayTradingWarning = await page.locator('[data-testid="day-trading-warning"]');
    if (await dayTradingWarning.isVisible()) {
      await expect(dayTradingWarning).toContainText('day trading');
    }
    
    await page.click('[data-testid="submit-order"]');
    await page.waitForSelector('[data-testid="order-confirmation"]');
    
    // Immediately try to sell (creating day trade)
    await page.click('[data-testid="new-order-button"]');
    await page.fill('[data-testid="symbol-input"]', 'SPY');
    await page.fill('[data-testid="quantity-input"]', '100');
    await page.selectOption('[data-testid="order-type"]', 'market');
    await page.selectOption('[data-testid="side"]', 'sell');
    
    await page.click('[data-testid="preview-order"]');
    
    // Should show day trading warning
    const secondDayTradingWarning = await page.locator('[data-testid="day-trading-warning"]');
    if (await secondDayTradingWarning.isVisible()) {
      await expect(secondDayTradingWarning).toContainText('day trade');
      await expect(secondDayTradingWarning).toContainText('pattern');
    }
  });

  test('should handle order execution notifications and updates', async () => {
    console.log('🔄 Testing order execution notifications...');
    
    await page.goto('/protected-portfolio');
    await page.waitForSelector('[data-testid="portfolio-container"]', { timeout: 30000 });
    
    // Place market order that should execute quickly
    await page.click('[data-testid="new-order-button"]');
    await page.fill('[data-testid="symbol-input"]', 'QQQ');
    await page.fill('[data-testid="quantity-input"]', '1');
    await page.selectOption('[data-testid="order-type"]', 'market');
    
    await page.click('[data-testid="preview-order"]');
    await page.click('[data-testid="submit-order"]');
    
    // Wait for order confirmation
    await page.waitForSelector('[data-testid="order-confirmation"]');
    
    // Listen for execution notification
    await page.waitForSelector('[data-testid="execution-notification"]', { timeout: 30000 });
    const notification = await page.locator('[data-testid="execution-notification"]');
    
    await expect(notification).toContainText('executed');
    await expect(notification).toContainText('QQQ');
    
    // Check execution details
    await page.click('[data-testid="order-history-tab"]');
    await page.waitForSelector('[data-testid="executed-orders-list"]');
    
    const executedOrder = page.locator('[data-testid="executed-order"]').filter({ hasText: 'QQQ' });
    await expect(executedOrder).toBeVisible();
    
    // Verify execution details are complete
    const executionPrice = await executedOrder.locator('[data-testid="execution-price"]');
    const executionTime = await executedOrder.locator('[data-testid="execution-time"]');
    
    await expect(executionPrice).toBeVisible();
    await expect(executionTime).toBeVisible();
    
    const priceText = await executionPrice.textContent();
    const timeText = await executionTime.textContent();
    
    expect(priceText).toMatch(/\$\d+\.\d{2}/);
    expect(timeText).toMatch(/\d{1,2}:\d{2}:\d{2}/);
  });
});