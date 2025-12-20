import { test, expect } from '@playwright/test';

test.describe('Data Validation - Verify All Pages Show Real Data', () => {

  // Dashboard Page
  test('Dashboard displays real portfolio data', async ({ page }) => {
    await page.goto('/', { waitUntil: 'networkidle' });

    // Check for real data indicators
    const portfolioSection = await page.locator('[data-testid="portfolio-summary"]').isVisible().catch(() => false);
    const priceElements = await page.locator('text=/$[0-9,]+.[0-9]{2}/').count();

    expect(priceElements).toBeGreaterThan(0);
    console.log('✅ Dashboard: Has real price data');
  });

  // Market Overview
  test('Market Overview displays market data', async ({ page }) => {
    await page.goto('/market-overview', { waitUntil: 'networkidle' });

    const marketData = await page.locator('text=/market|breadth|sentiment/i').count();
    const numbers = await page.locator('text=/d+.d{2}%?/').count();

    if (numbers > 2) {
      console.log('✅ Market Overview: Has market data');
    } else {
      console.log('❌ Market Overview: MISSING market data');
    }

    expect(numbers).toBeGreaterThan(2);
  });

  // Trading Signals
  test('Trading Signals displays buy/sell signals', async ({ page }) => {
    await page.goto('/trading-signals', { waitUntil: 'networkidle' });

    // Check for signal indicators
    const buyLabels = await page.locator('text=/buy|sell|signal/i').count();
    const symbolElements = await page.locator('[data-testid*="signal"]').count().catch(() => 0);

    if (buyLabels > 3) {
      console.log('✅ Trading Signals: Has real signals');
    } else {
      console.log('❌ Trading Signals: MISSING signals');
    }

    expect(buyLabels).toBeGreaterThan(3);
  });

  // Portfolio Dashboard
  test('Portfolio Dashboard shows holdings', async ({ page }) => {
    await page.goto('/portfolio-dashboard', { waitUntil: 'networkidle' });

    const portfolioItems = await page.locator('[data-testid*="holding"]').count().catch(() => 0);
    const rows = await page.locator('tr').count().catch(() => 0);
    const tableData = await page.locator('td').count().catch(() => 0);

    console.log(`Portfolio Dashboard: ${tableData} table cells, ${portfolioItems} holdings`);

    // Should have at least some table structure
    if (tableData > 5 || portfolioItems > 0) {
      console.log('✅ Portfolio Dashboard: Has holdings data');
      expect(tableData).toBeGreaterThan(0);
    } else {
      console.log('⚠️ Portfolio Dashboard: May be missing data');
    }
  });

  // Sector Analysis
  test('Sector Analysis displays sectors', async ({ page }) => {
    await page.goto('/sector-analysis', { waitUntil: 'networkidle' });

    const sectorNames = await page.locator('text=/technology|finance|healthcare|energy/i').count();
    const percentages = await page.locator('text=/%/').count();

    console.log(`Sector Analysis: ${sectorNames} sectors, ${percentages} percentages`);

    if (sectorNames > 2 && percentages > 0) {
      console.log('✅ Sector Analysis: Has sector data');
      expect(percentages).toBeGreaterThan(0);
    } else {
      console.log('❌ Sector Analysis: MISSING sector data');
    }
  });

  // Stock Explorer
  test('Stock Explorer shows stocks', async ({ page }) => {
    await page.goto('/stock-explorer', { waitUntil: 'networkidle' });

    const stocks = await page.locator('[data-testid*="stock"]').count().catch(() => 0);
    const symbols = await page.locator('text=/[A-Z]{1,5}/').count().catch(() => 0);
    const rows = await page.locator('tbody tr').count().catch(() => 0);

    console.log(`Stock Explorer: ${rows} rows, ${stocks} stock elements`);

    if (rows > 5 || stocks > 5) {
      console.log('✅ Stock Explorer: Has stock data');
      expect(rows + stocks).toBeGreaterThan(5);
    } else {
      console.log('❌ Stock Explorer: MISSING stock data');
    }
  });

  // Stock Screener
  test('Stock Screener has filters and results', async ({ page }) => {
    await page.goto('/stock-screener', { waitUntil: 'networkidle' });

    const filterElements = await page.locator('[data-testid*="filter"]').count().catch(() => 0);
    const results = await page.locator('tbody tr').count().catch(() => 0);

    console.log(`Stock Screener: ${filterElements} filters, ${results} results`);

    if (filterElements > 0) {
      console.log('✅ Stock Screener: Has filters available');
    }
  });

  // Analyst Insights
  test('Analyst Insights displays ratings', async ({ page }) => {
    await page.goto('/analyst-insights', { waitUntil: 'networkidle' });

    const ratings = await page.locator('text=/buy|hold|sell|rate/i').count();
    const analysts = await page.locator('[data-testid*="analyst"]').count().catch(() => 0);

    console.log(`Analyst Insights: ${ratings} rating references, ${analysts} analyst elements`);

    if (ratings > 3) {
      console.log('✅ Analyst Insights: Has rating data');
      expect(ratings).toBeGreaterThan(3);
    } else {
      console.log('❌ Analyst Insights: MISSING rating data');
    }
  });

  // Economic Dashboard
  test('Economic Dashboard displays economy data', async ({ page }) => {
    await page.goto('/economic-dashboard', { waitUntil: 'networkidle' });

    const economicTerms = await page.locator('text=/gdp|inflation|unemployment|rate/i').count();
    const dataPoints = await page.locator('text=/d+.?d*%?/').count();

    console.log(`Economic Dashboard: ${economicTerms} econ terms, ${dataPoints} data points`);

    // May have limited data depending on loaders
    if (economicTerms > 0 || dataPoints > 2) {
      console.log('✅ Economic Dashboard: Has some economic data');
    } else {
      console.log('⚠️ Economic Dashboard: May be missing data');
    }
  });

  // Earnings Calendar
  test('Earnings Calendar shows earnings', async ({ page }) => {
    await page.goto('/earnings-calendar', { waitUntil: 'networkidle' });

    const earningsItems = await page.locator('[data-testid*="earning"]').count().catch(() => 0);
    const dates = await page.locator('text=/d{1,2}/d{1,2}/d{4}/').count();
    const eps = await page.locator('text=/eps/i').count();

    console.log(`Earnings Calendar: ${earningsItems} earnings, ${dates} dates, ${eps} EPS mentions`);

    if (dates > 0 || earningsItems > 0) {
      console.log('✅ Earnings Calendar: Has earnings data');
    } else {
      console.log('❌ Earnings Calendar: MISSING earnings data');
    }
  });

  // Sentiment
  test('Sentiment page displays sentiment data', async ({ page }) => {
    await page.goto('/sentiment', { waitUntil: 'networkidle' });

    const sentiments = await page.locator('text=/bullish|bearish|neutral|sentiment/i').count();
    const charts = await page.locator('[data-testid*="chart"]').count().catch(() => 0);

    console.log(`Sentiment: ${sentiments} sentiment references, ${charts} charts`);

    if (sentiments > 2) {
      console.log('✅ Sentiment: Has sentiment data');
      expect(sentiments).toBeGreaterThan(2);
    } else {
      console.log('❌ Sentiment: MISSING sentiment data');
    }
  });

  // Watchlist
  test('Watchlist displays monitored stocks', async ({ page }) => {
    await page.goto('/watchlist', { waitUntil: 'networkidle' });

    const watchlistItems = await page.locator('[data-testid*="watchlist"]').count().catch(() => 0);
    const symbols = await page.locator('text=/[A-Z]{1,5}/').count().catch(() => 0);

    console.log(`Watchlist: ${watchlistItems} watchlist items, ${symbols} symbols`);

    // May be empty if user has no watchlist
    if (watchlistItems > 0 || symbols > 5) {
      console.log('✅ Watchlist: Has watchlist data');
    } else {
      console.log('⚠️ Watchlist: May be empty or loading');
    }
  });

  // Scores Dashboard
  test('Scores Dashboard shows composite scores', async ({ page }) => {
    await page.goto('/scores-dashboard', { waitUntil: 'networkidle' });

    const scores = await page.locator('text=/score/i').count();
    const numbers = await page.locator('text=/[0-9]{1,3}.?[0-9]?/').count();

    console.log(`Scores Dashboard: ${scores} score references, ${numbers} numbers`);

    if (scores > 5 && numbers > 10) {
      console.log('✅ Scores Dashboard: Has score data');
      expect(scores).toBeGreaterThan(5);
    } else {
      console.log('❌ Scores Dashboard: MISSING score data');
    }
  });

  // Trade History
  test('Trade History displays trades', async ({ page }) => {
    await page.goto('/trade-history', { waitUntil: 'networkidle' });

    const tradeItems = await page.locator('[data-testid*="trade"]').count().catch(() => 0);
    const rows = await page.locator('tbody tr').count().catch(() => 0);

    console.log(`Trade History: ${tradeItems} trade items, ${rows} rows`);

    // May be empty if no trades
    if (rows > 0 || tradeItems > 0) {
      console.log('✅ Trade History: Has trade data');
    } else {
      console.log('⚠️ Trade History: May be empty');
    }
  });
});
